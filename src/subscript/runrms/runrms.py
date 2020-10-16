#!/usr/bin/env python

import sys
import time
import datetime
import platform
import os
import tempfile
import argparse
import subprocess
import shutil
import getpass
from glob import glob

from os.path import join, isdir

DESCRIPTION = """
Script to run rms project from command line, which will in turn use the
'rms...' command OR will look at /prog/roxar/site. Note that not all
options valid for 'rms' will be covered.

* It should understand current RMS version in project and launch correct
  RMS executable
* It should be able to run test versions of RMS
* It should be able to set the correct Equinor valid PYTHONPATH.
* Company wide plugin path

Example of usage::

   runrms newreek.rms10.1.3 (if new project: warn and just start rms default)
   runrms reek.rms10.1.3  (automaically detect version from .master)
   runrms -project reek.10.1.3  (same as previous)
   runrms reek.rms10.1.3 -v 11.0.1 (force version 11.0.1)

"""


RMS10PY = "python3.4"
RMS11PY = "python3.6"
RMS12PY = "python3.6"
THISSCRIPT = os.path.basename(sys.argv[0])
BETA = "RMS_test_latest"
SITE = "/prog/roxar/site/"
ROXAPISITE = "/project/res/roxapi"
RHEL_ID = "/etc/redhat-release"

# Note
# From October/November 2020: If disable_komodo_exec is present, RMS will be launched
# with komodo disabled. To make run_external (which enables komodo again for that
# particular command) work when komodo is disabled, it is installed separately in a
# PATH in RUN_EXTERNAL_PATH. A temp-file is used to start RMS with the augmented path,
# modifying env directly from Python may not work.

RUN_EXTERNAL_PATH = "export PATH=/project/res/roxapi/bin:$PATH"
RUN_EXTERNAL_CMD = "/project/res/roxapi/bin/run_external"


def touch(fname):
    """Touch a file on filesystem, updating its timestamp or
    creating if it does not exist"""
    try:
        os.utime(fname, None)
    except OSError:
        open(fname, "a").close()


def xwarn(mystring):
    """Print a warning with colors"""
    print(_BColors.WARN, mystring, _BColors.ENDC)


def xerror(mystring):
    """Print an error in an appropriate color"""
    print(_BColors.ERROR, mystring, _BColors.ENDC)


def detect_os():
    """Detect operating system string in runtime, return None if not found"""

    # currently only supporting REDHAT systems
    if os.path.exists(RHEL_ID):
        with open(RHEL_ID, "r") as buffer:
            major = buffer.read().split(" ")[6].split(".")[0].replace("'", "")
            return "x86_64_RH_" + str(major)

    else:
        return None


def get_parser():
    """Make a parser for command line arguments and for documentation"""
    prs = argparse.ArgumentParser(description=DESCRIPTION)

    # positional:
    prs.add_argument("project", type=str, nargs="?", help="RMS project name")

    prs.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="If you want to run this script in verbose mode",
    )

    prs.add_argument(
        "--dryrun",
        dest="dryrun",
        action="store_true",
        help="Run this script without actually launching RMS",
    )

    prs.add_argument(
        "--version", "-v", dest="rversion", type=str, help="RMS version, e.g. 10.1.3"
    )

    prs.add_argument(
        "--beta",
        dest="beta",
        action="store_true",
        help="Will try latest RMS beta version",
    )

    prs.add_argument(
        "--fake",
        dest="fake",
        action="store_true",
        help="This is for CI testing only, will not look for rms executable",
    )

    prs.add_argument(
        "--project",
        "-project",
        dest="rproject2",
        type=str,
        help="Name of RMS project (alternative launch)",
    )

    prs.add_argument(
        "--readonly",
        "-r",
        "-readonly",
        dest="ronly",
        action="store_true",
        help="Read only mode (disable save)",
    )

    prs.add_argument(
        "--dpiscaling",
        "-d",
        dest="sdpi",
        type=float,
        help="Spesify RMS DPI display scaling as percent, where 100 is no scaling",
    )

    prs.add_argument(
        "--batch",
        "-batch",
        dest="bworkflows",
        nargs="+",
        type=str,
        help=(
            "Runs project in batch mode (req. project) " "with workflows as argument(s)"
        ),
    )

    prs.add_argument(
        "--nopy",
        dest="nopy",
        action="store_true",
        help="If you want to run RMS withouth any modication " "of current PYTHONPATH",
    )

    prs.add_argument(
        "--includesyspy",
        dest="incsyspy",
        action="store_true",
        help="If you want to run RMS and include current "
        "system PYTHONPATH (typically Komodo based)",
    )

    prs.add_argument(
        "--testpylib",
        dest="testpylib",
        action="store_true",
        help="If you want to run RMS and use a test version of the Equinor "
        "installed Python modules for RMS, e.g. test XTGeo (NB special usage!)",
    )
    return prs


class _BColors:
    # pylint: disable=too-few-public-methods
    # local class for ANSI term color commands

    HEADER = "\033[93;42m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARN = "\033[93;43m"
    ERROR = "\033[93;41m"
    CRITICAL = "\033[1;91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class RunRMS:
    """A class for setting up an environment in which to execute RMS"""

    def __init__(self):
        self.version_requested = None  # RMS version requested
        self.pythonpath = None  # RMS pythonpath
        self.pluginspath = None  # RMS pythonpath
        self.args = None  # The cmd line arguments
        self.project = None  # The path to the RMS project
        self.version_fromproject = None  # Actual ver from the .master (number/string)
        self.defaultver = None  # RMS default version
        self.fileversion = None  # Internal RMS file version
        self.variant = None  # Executable variant
        self.user = None  # user id
        self.date = None  # Date last opened
        self.time = None  # time last opened
        self.lockf = None  # lockfile
        self.locked = False  # locked (bool)
        self.exe = None  # RMS executable
        self.okext = True  # hmm
        self.extstatus = "OK"
        self.beta = BETA
        self.rmsinstallsite = SITE
        self.command = "rms"
        self.setdpiscaling = ""
        self.runloggerfile = "/prog/roxar/site/log/runrms_usage.log"

        self.oldpythonpath = ""
        if "PYTHONPATH" in os.environ:
            self.oldpythonpath = os.environ["PYTHONPATH"]

        # Set environment variables for use by `run_external`
        # from equinor/equilibrium:
        if "PYTHONPATH" in os.environ:
            os.environ["_PRE_RMS_PYTHONPATH"] = os.environ["PYTHONPATH"]
        else:
            os.environ["_PRE_RMS_PYTHONPATH"] = ""
        os.environ["_PRE_RMS_BACKUP"] = "1"

        print(
            _BColors.BOLD,
            "\nRunning <{0}>. Type <{0} -h> for help\n".format(THISSCRIPT),
            _BColors.ENDC,
        )

    def do_parse_args(self, args):
        """Parse command line args"""
        if args is None:
            args = sys.argv[1:]

        prs = get_parser()

        args = prs.parse_args(args)

        self.args = args

    def debug(self, string):
        """Verbose mode for debugging..."""
        try:
            if self.args.debug:
                print(string)
        except AttributeError:
            pass

    def scan_rms(self):
        """Scan the RMS project's .master and returns some basic data needed
        for launching the RMS project"""

        def _fsplitter(xline):  # yes... an inner function
            if len(xline) == 3:
                return xline[2]
            return "unknown"

        # first check if folder exists, and issue a warning if not
        if not os.path.isdir(self.project):
            print("Project does not exist, will only launch RMS!")
            self.project = None
            return None

        mkeys = ("fileversion", "variant", "user", "date", "time")
        try:
            with open(join(self.project, ".master"), "rb") as master:
                for line in master.read().decode("UTF-8").splitlines():
                    if line.startswith("End GEOMATIC"):
                        break
                    if line.startswith("release"):
                        rel = list(line.split())
                        self.version_fromproject = rel[2]
                        self.complete_version_fromproject()
                    for mkey in mkeys:
                        if line.startswith(mkey):
                            setattr(self, mkey, _fsplitter(line.split()))

        except EnvironmentError as err:
            xerror("Stop! Cannot open .master file: {}".format(err))
            print("Possible causes:")
            print(" * Project is not existing")
            print(" * Project is corrupt")
            print(
                " * Project is RMS 2013.0.x version (incompatible with " "this script)"
            )
            raise SystemExit

        try:
            with open(join(self.project, "project_lock_file"), "r") as lockf:
                for line in lockf.readlines():
                    self.lockf = line.replace("\n", "")
                    self.locked = True
                    break
        except EnvironmentError:
            pass

    def complete_version_fromproject(self):
        """For RMS 10.0.0 and 11.0.0 (etc) the release is reported as
        10 or 11 in the .master file. Extend this to always have 3
        fields e.g. 10 --> 10.0.0
        """

        # valid for beta versions:
        if not self.version_fromproject[0].isdigit():
            return

        # officials:
        numdots = self.version_fromproject.count(".")
        rls = self.version_fromproject
        if numdots == 0:
            rls = "{}{}".format(self.version_fromproject, ".0.0")
        elif numdots == 1:
            rls = "{}{}".format(self.version_fromproject, ".0")

        self.version_fromproject = rls
        return

    def get_rms_exe(self):
        """Get the correct RMS executable"""

        if self.args.fake:
            return

        if self.args.beta:
            ok2 = self._get_rms_exe_nonstandard()
            ok1 = True
        else:
            ok1 = self._get_rms_exe_standard()

        # try versions in /prog/roxar/site/rms/ (self.rmsinstallsite)
        ok2 = False
        if not ok1:
            xwarn(
                "Cannot find correct RMS version in standard installs, "
                "trying nonstandard installation path at your own risk... "
            )
            print("")
            ok2 = self._get_rms_exe_nonstandard()

        if not ok2 and not ok1:
            self._list_nonstandards()
            xerror(
                "Cannot find requested RMS version: {}".format(self.version_requested)
            )
            raise SystemExit("EXIT")
        return

    def _get_rms_exe_standard(self):
        """Check rms -v command..."""

        output = subprocess.check_output(["rms", "-v"], universal_newlines=True)
        output = output.split("\n")
        look = False

        self.debug("RMS -v: \n\n{}\n\n".format(output))
        self.exe = None
        defaultversion = None
        installed = []
        for line in output:
            if line.startswith("Available"):
                look = True
                continue
            if look:
                line = line.strip(" ")
                usedefault = "default" in line

                line = line.replace("(default)", "")
                line = line.replace("\t", "")
                line = line.replace(" ", "")
                if line and line[0].isdigit():
                    installed.append(line)
                if usedefault:
                    defaultversion = line

        self.defaultver = defaultversion

        self.debug("Installed versions {}".format(installed))
        self.debug("Default version {}".format(defaultversion))
        self.debug("Version requested <{}>".format(self.version_requested))
        self.debug("Version in project <{}>".format(self.version_fromproject))
        self.debug("Exe {}".format(self.exe))
        if self.version_requested in installed:
            print("Current RMS from standard install...")
            self.exe = "rms -v " + self.version_requested
            return True

        return False

    def _get_rms_exe_nonstandard(self):
        """Running RMS from nonstandards versions"""

        if self.args.beta:
            # BETA version, assume latest
            self.version_requested = BETA
            self.exe = "/prog/roxar/site/" + self.beta + "/rms/rms"

        else:
            psals = [
                self.rmsinstallsite + "RMS" + self.version_requested + "/rms/rms",
                self.rmsinstallsite + "rms" + self.version_requested + "/rms/rms",
            ]

            for prop in psals:
                print("Try {} ...".format(prop))
                if os.path.isfile(prop):
                    self.exe = prop
                    break

        if self.exe is None:
            print(
                "Sorry, cannot find a RMS executable. Try use another " "version as -v"
            )

            return False

        xwarn("Getting RMS version from nonstandard install...")

        return True

    def _list_nonstandards(self):
        """Listing nonstandard installs"""

        print(
            "{0}\nPossible versions (no guarantee they will "
            "work):\n{0}".format("=" * 80)
        )
        for item in glob(self.rmsinstallsite + "*"):
            if os.path.isdir(item) and os.path.exists(item + "/rms/rms"):
                version = item.replace(self.rmsinstallsite, "")
                version = version.replace("RMS", "")
                print(" * {0:45s}   {1:10s}".format(item, version))
        print("{0}\n".format("=" * 80))

    def get_scaledpi(self):
        """Get and check dpiscaling"""

        usedpi = 100
        if self.args.sdpi:
            tmpdpi = self.args.sdpi
            if isinstance(tmpdpi, float) and 20 <= tmpdpi <= 500:
                usedpi = tmpdpi

            self.setdpiscaling = "QT_SCALE_FACTOR={} ".format(usedpi / 100.0)

    def _detect_pyver_from_path(self):
        """
        Loop through the folder in the /project/res/roxapi and get py version
        from that. Hence with new RMS versions, it should not be necessary
        to hardcode python version in *this* script, but rather make the correct
        folders. It requires/assumes that setup in /project/res/roxapi is correct
        """
        if detect_os() is None:
            return "python3.6"

        sdirs = [ROXAPISITE, detect_os(), self.version_requested, "lib"]

        searchdir = join(*sdirs)

        if not isdir(searchdir):
            raise RuntimeError(
                "Seems that this version <{}> is not in {}".format(
                    self.version_requested, ROXAPISITE
                )
            )

        possible_py3v = list(["3." + str(minor) for minor in range(4, 20)])

        self.debug("Search dir for Python version is {}".format(searchdir))
        self.debug("Possible python versions: {}".format(possible_py3v))

        for pyv in possible_py3v:
            testpath = join(searchdir, "python" + pyv)
            if isdir(testpath):
                return testpath

        raise RuntimeError("Cannot find valid PYTHONPATH for {}".format(searchdir))

    def get_pythonpath(self):
        """Get correct pythonpath and pluginspath for the given RMS version"""
        usepy = RMS10PY
        thereleasepy = self.version_requested
        possible_versions = tuple([str(num) for num in range(10, 20)])

        if (
            self.version_requested.startswith(possible_versions)
            or not self.version_requested[0].isdigit()
        ):

            if not self.version_requested[0].isdigit():
                self.version_requested = "beta"

            try:
                usepy = self._detect_pyver_from_path()
            except ValueError:
                print("Cannot detect valid pythonpath...")
            else:
                thereleasepy = self.version_requested

        else:
            usepy = RMS12PY
            thereleasepy = "12.0.1"

        osver = detect_os()
        if osver is None:
            xwarn("Cannot find valid OS version , set to 'dummy'")
            osver = "dummy"
        else:
            print("OS platform is {}\n".format(osver))

        ospath = os.path.join(ROXAPISITE, osver)

        python3path = join(ospath, thereleasepy, "lib", usepy, "site-packages")

        python3pathtest = join(
            ospath, thereleasepy + "_test", "lib", usepy, "site-packages"
        )

        pluginspath = join(ospath, thereleasepy, "plugins")

        self.debug("PYTHON3 PATH: {}".format(python3path))
        self.pythonpath = python3path
        self.pythonpathtest = python3pathtest
        self.pluginspath = pluginspath

        if not os.path.isdir(python3path):
            self.pythonpath = ""
            xwarn(
                "Equinor PYTHONPATH for RMS ({}) not existing, set empty".format(
                    python3path
                )
            )

        if not os.path.isdir(pluginspath):
            self.pluginspath = ""
            xwarn(
                "Equinor RMS_PLUGINS_PATH for RMS ({}) not existing, set empty".format(
                    pluginspath
                )
            )

    def launch_rms(self, empty=False):
        """Launch RMS with correct pythonpath"""

        if self.exe is None:
            self.exe = "rms -v " + self.version_requested

        command = self.setdpiscaling + "RMS_IPL_ARGS_TO_PYTHON=1 "

        if self.pluginspath:
            command += "RMS_PLUGINS_LIBRARY=" + self.pluginspath + " "

        if not self.args.nopy:
            command += "PYTHONPATH="
            if self.args.testpylib:
                command += self.pythonpathtest + ":" + self.pythonpath
            else:
                command += self.pythonpath
            if self.args.incsyspy:
                command += ":" + self.oldpythonpath

        command += " " + self.exe
        if self.args.ronly:
            command += " -readonly"
        if self.args.bworkflows:
            command += " -batch"
            for bjobs in self.args.bworkflows:
                command += " " + bjobs

        if not empty:
            command += " -project " + self.project

        self.command = command
        print(_BColors.BOLD, "\nRunning: {}\n".format(command), _BColors.ENDC)
        print("=" * 132)

        if self.locked:
            xwarn(
                "NB! Opening a locked RMS project (you have 5 seconds to press "
                "Ctrl-C to abort)"
            )
            for sec in range(5, 0, -1):
                time.sleep(1)
                print("... {}".format(sec))

        if self.args.dryrun:
            xwarn("<<<< DRYRUN, do not start RMS >>>>")
            user = getpass.getuser()
            self.runloggerfile = "/tmp/runlogger_" + user + ".txt"
            touch(self.runloggerfile)

        else:
            print(_BColors.OKGREEN)

            # To make run_external work in a Komodo setting:
            # make a tmp file which also sets path; to be combined with run_external

            if shutil.which("disable_komodo_exec"):

                if not shutil.which(RUN_EXTERNAL_CMD):
                    raise RuntimeError(f"The script {RUN_EXTERNAL_CMD} is not present")

                fhandle, fname = tempfile.mkstemp(text=True)
                with open(fname, "w+") as fxx:
                    fxx.write(RUN_EXTERNAL_PATH + "\n")
                    fxx.write(self.command)

                os.close(fhandle)
                os.system("chmod u+rx " + fname)
                os.system("disable_komodo_exec " + fname)
                if self.args.debug:
                    os.system("cat " + fname)
                os.unlink(fname)
            else:
                # backup is to run the old way
                os.system(self.command)

            print(_BColors.ENDC)

    def showinfo(self):
        """Show info on RMS project"""

        print("=" * 132)
        print("Script runrms from subscript")
        print("=" * 132)
        print("{0:30s}: {1}".format("Project name", self.project))
        print("{0:30s}: {1}".format("Last saved by", self.user))
        print("{0:30s}: {1} {2}".format("Last saved date & time", self.date, self.time))
        print("{0:30s}: {1}".format("Locking info", self.lockf))
        if not self.okext:
            print(
                "{0:30s}: {2}{1}{3}".format(
                    "File extension status",
                    self.extstatus,
                    _BColors.UNDERLINE,
                    _BColors.ENDC,
                )
            )

        print("{0:30s}: {1}".format("Equinor current default ver.", self.defaultver))
        print("{0:30s}: {1}".format("RMS version in project", self.version_fromproject))
        print("{0:30s}: {1}".format("RMS version (requested)", self.version_requested))
        print("{0:30s}: {1}".format("RMS internal storage ID", self.fileversion))
        print("{0:30s}: {1}".format("RMS executable variant", self.variant))
        print("{0:30s}: {1}".format("System pythonpath*", self.oldpythonpath))
        print("{0:30s}: {1}".format("Pythonpath added as first**", self.pythonpath))
        print("{0:30s}: {1}".format("RMS executable", self.exe))
        print("=" * 132)
        print("NOTES:")
        print("*   Will be added if --includesyspy option is used")
        print("**  Will be added unless --nopy option is used")
        print("=" * 132)

    def check_vconsistency(self):
        """Check consistency of file extension vs true version"""

        # check file name vs release
        wanted = "rms" + self.version_requested
        if self.project.endswith(wanted):
            self.extstatus = (
                "Good, project name extension is consistent with actual RMS version"
            )
            self.okext = True
        else:
            self.extstatus = (
                "UPS, project name extension is inconsistent "
                "with actual RMS version: <{}> vs version <{}>"
            ).format(self.project, wanted)
            self.okext = False

    def runlogger(self):
        """Add a line to /prog/roxar/site/log/runrms_usage.log"""

        # date,time,user,host,full_rms_exe,commandline_options

        now = datetime.datetime.now()
        nowtime = now.strftime("%Y-%m-%d,%H:%M:%S")
        user = getpass.getuser()
        host = platform.node()

        myargs = self.command
        # for key, val in vars(self.args).items():
        #     if key == "project":
        #         myargs = myargs + str(val) + " "
        #     if val is not None and val is True:
        #         myargs = myargs + "--" + str(key) + " " + str(val) + " "

        lline = "{},{},{},{},{},{}\n".format(
            nowtime, user, host, "client", self.exe, myargs
        )

        if not os.path.isfile(self.runloggerfile):
            # if file is missing, simply skip!
            return

        with open(self.runloggerfile, "a") as logg:
            logg.write(lline)

        self.debug("Logging usage to {}:".format(self.runloggerfile))
        self.debug(lline)


def main(args=None):
    """Running RMS version ..."""

    runner = RunRMS()

    runner.do_parse_args(args)

    runner.version_requested = runner.args.rversion

    runner.debug("ARGS: {}".format(runner.args))

    runner.project = runner.args.project
    if runner.args.rproject2:
        runner.project = runner.args.rproject2

    if runner.project:
        runner.project = runner.project.rstrip("/")
        runner.scan_rms()

    if runner.project is None and runner.version_requested is None:
        runner.version_requested = "10.1.3"
        runner.exe = "rms -v 10.1.3"

    if runner.version_requested is None:
        runner.version_requested = runner.version_fromproject

    runner.get_pythonpath()

    emptyproject = True
    if runner.project is not None:
        runner.check_vconsistency()
        emptyproject = False
    else:
        runner.version_fromproject = runner.version_requested
    runner.get_rms_exe()
    runner.get_scaledpi()
    runner.showinfo()
    runner.launch_rms(empty=emptyproject)

    runner.runlogger()


if __name__ == "__main__":
    main()
