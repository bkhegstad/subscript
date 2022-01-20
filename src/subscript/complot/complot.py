"""Complot is a plotting tool for Completor to visualise flow along a multi-segmented well path."""

from io import StringIO
from copy import deepcopy
import math
import sys
from typing import Dict

from ecl.summary import EclSum
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import rcParams
from matplotlib import ticker
import numpy as np
import pandas as pd
import file_processing as fp
import schedule_reader as sr

fontP = FontProperties()
fontP.set_size(6)

PI = math.pi


def update_fonts(family="DejaVu Serif", size=12):
    """
    Update font type and size.

    Args:
        family (str): Font family
        size (int): Font size

    Returns:
        None
    """

    rcParams["font.family"] = family
    rcParams.update({"font.size": size})


def format_subplot(
    axis,
    title,
    x_label,
    y_label,
    x_lim=(),
    y_lim=(),
    categorical=False,
    max_val=1.0,
    min_val=0.0,
    legend=True,
    legend_location="right",
):
    """
    Format a subplot with labels, limits and legend.

    Args:
        axis (AxesSubplot): An axis object
        title (str): Subplot title
        x_label (str): X-axis label
        y_label (str): Y-axis label
        x_lim (tuple): X-axis view limits
        y_lim (tuple): Y-axis view limits
        categorical (bool): Minor ticks activated on False (default)
        max_val (float): Maximum Y-axis view limit
        min_val (float): Minimum Y-axis view limit
        legend (bool): Legend activator
        legend_location (str): Legend location

    Returns:
        None
    """
    min_val, max_val = axis.get_ylim()
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)

    if categorical:
        axis.minorticks_on()
        axis.tick_params(
            axis="both", which="major", direction="in", length=6, width=1.0
        )
        axis.tick_params(
            axis="both", which="minor", direction="in", length=3, width=1.0
        )
        major = (max_val - min_val) / 5.0
        if major < 1.0:
            major = round(major, 1)
            if abs(major - 1.0) < abs(major - 0.5):
                major = 1.0
            else:
                if abs(major - 0.5) < abs(major - 0.25):
                    major = 0.5
                else:
                    major = 0.25
        else:
            major = round(major, 0)
        print(major)
        axis.yaxis.set_major_locator(ticker.MultipleLocator(major))
        axis.minorticks_off()
    else:
        axis.minorticks_on()
        axis.tick_params(
            axis="both", which="major", direction="in", length=6, width=1.0
        )
        axis.tick_params(
            axis="both", which="minor", direction="in", length=3, width=1.0
        )
    axis.yaxis.set_ticks_position("both")
    axis.xaxis.set_ticks_position("both")
    if len(x_lim) > 0:
        axis.set_xlim(x_lim)
    if len(y_lim) > 0:
        axis.set_ylim(y_lim)
    axis.grid(which="both", linestyle="-", linewidth=0.1, color="grey", alpha=0.1)
    if legend:
        if legend_location == "top":
            axis.legend(
                numpoints=1,
                bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
                loc=3,
                ncol=2,
                mode="expand",
                borderaxespad=0,
                framealpha=0.2,
            )
        elif legend_location == "right":
            axis.legend(loc="center left", bbox_to_anchor=(1, 0.5))
    axis.set_title(title)


class SegmentPlot:
    """
    Class with methods for parsing the input file and plotting data along the well path.

    Attributes:
        input_file (str): The input file name containing the keywords DATAFILE,
            WELLFILE, OUTPUTFILE, and INFORMATION.
        output_pdf (str): The pdf output file name.
        clean_input_file (object): A clean version of the input file content in
            io.StringIO format.
        read_clean_input (list): A list of lines in the cleaned input file.
        datafile_kw: Method for reading the input file DATAFILE keyword
            content.
        casename_kw: Method for reading the input file CASENAME keyword
            content.
        wellfile_kw: Method for reading the input file WELLFILE keyword
            content.
        outputfile_kw: Method for reading the input file OUTPUTFILE
            keyword content.
        information_kw: Method for reading the input file INFORMATION
            keyword content.

    Returns:
        Class object with input file information and methods for plotting.
    """

    def __init__(self, input_file):
        self.input_file_name = input_file
        self.output_pdf = input_file.split(".")[0] + ".pdf"
        self.clean_input_file = fp.clear_comments(input_file)
        self.read_clean_input = self.clean_input_file.readlines()
        self.data_file = []
        self.n_file = 0
        self.case_name = ""
        self.information = None
        self.eclipse = None
        self.eclipse_dates = None
        self.eclipse_days = None
        self.df_well = None
        self.list_keywords = []
        self.kw_valid = []
        self.df_annulus_zone = None
        self.my_days_idx = None
        self.df_tubing = None
        self.df_device = None
        self.df_annulus = None
        self.df_reservoir = None
        self.output_file = None
        self.well_file = []
        self.compdat_table = None
        self.compsegs_table = None
        self.welsegs_header = None
        self.welsegs_table = None
        self.datafile_kw()
        self.casename_kw()
        self.well_file_kw()
        self.output_file_kw()
        self.information_kw()

    def datafile_kw(self):
        """
        Parse the cleaned input file in list-line format and returns a list of datafiles found in the DATAFILE keyword.

        Returns:
            A list of data files read from the DATAFILE keyword in the input file.

        Raises:
            ValueError: If the list of data files (data_file) is empty.
        """

        mydata = deepcopy(self.read_clean_input)
        n_line = len(mydata)

        self.data_file = []
        for i in range(n_line):
            mydata[i] = mydata[i].strip("\n")
        for i in range(n_line):
            if mydata[i] == "DATAFILE":
                i = i + 1
                while str(mydata[i]) != "/":
                    self.data_file.append(str(mydata[i]).replace("'", ""))
                    i = i + 1
        self.n_file = len(self.data_file)
        if self.n_file == 0:
            raise ValueError("Error : Eclipse file is not specified")

    def casename_kw(self):
        """Read the CASENAME keyword content in the input file."""

        mydata = deepcopy(self.read_clean_input)
        n_line = len(mydata)
        self.case_name = []
        for i in range(n_line):
            mydata[i] = mydata[i].strip("\n")
        for i in range(n_line):
            if mydata[i] == "CASENAME":
                i = i + 1
                while str(mydata[i]) != "/":
                    self.case_name.append(str(mydata[i]).replace("'", ""))
                    i = i + 1
        if len(self.case_name) == 0:
            self.case_name = deepcopy(self.data_file)

    def read_data_file(self, data_file):
        """
        Read a datafile using the method EclSum from ecl.

        Args:
            data_file (str): Data file name.

        Returns:
            Data file content.\n
            Array of simulation days.\n
            Array of Eclipse format dates.\n
        """

        self.eclipse = EclSum(data_file)
        self.eclipse_days = np.asarray(self.eclipse.days)
        self.eclipse_dates = self.eclipse.dates

    def read_well_file(self, well_file):
        """
        Read an Eclipse schedule file keywords COMPDAT, COMPSEGS and WELSEG.

        Args:
            well_file (str): Schedule file name.

        Returns:
            The WELSEGS header line.\n
            The WELSEGS body.\n
            The COMPSEGS keyword content.\n
            The COMPDAT keyword content.\n
        """
        sch = fp.clear_comments(well_file)
        sch = sch.readlines()
        sch = sr.read_schedule_keywords(sch, ["COMPDAT", "COMPSEGS", "WELSEGS"])
        self.welsegs_header, self.welsegs_table = sr.welsegs_panda(sch)
        self.compsegs_table = sr.compsegs_panda(sch)
        self.compdat_table = sr.compdat_panda(sch)

    def clean_trailing(self, dirty_str: str) -> str:
        """
        Cleans trailing spaces, tabs and newline markers.

        Args:
            dirty_str (str): A dirty string

        Returns:
            A clean string
        """

        clean_str = dirty_str.replace(" ", "")
        clean_str = clean_str.replace("\t", "")
        clean_str = clean_str.replace("\n", "")
        return clean_str

    def relative_path(self, datafile: str) -> Dict[str, str]:
        """
        Find the relative path from the PATHS keyword in the Eclipse data file.

        Args:
            datafile (str): Eclipse data file name.

        Returns:
            A dictionary of paths in PATHS.
        """

        ecl = fp.clear_comments(datafile)
        ecl = ecl.readlines()
        path_dict = {}
        for idx, idx_line in enumerate(ecl):
            keyword = idx_line.replace(" ", "")
            keyword = keyword.replace("\t", "")
            keyword = keyword.replace("\n", "")
            if keyword == "PATHS" and idx < (len(ecl) - 2):
                idx = idx + 1
                while self.clean_trailing(ecl[idx]) != "/":
                    content = ecl[idx].replace("\t", " ")
                    content = content.replace("'", "")
                    content = content.replace('"', "")
                    content = content.split(" ")
                    content = list(filter(None, content))
                    path_dict[content[0]] = content[1]
                    idx = idx + 1
        return path_dict

    def well_file_kw(self):
        """
        Read the content of the WELLFILE keyword in the input file to complot.

        Uses read_clean_input, a StringIO object of the input file.

        Returns:
            A list of WellFile strings for each schedule file
            listed in the WELLFILE keyword.

        Raises:
            ValueError: If no schedule file is found.
            ValueError: If the number of data files in the DATAFILE keyword does
                not match the number of schedule files.
        """

        my_data = deepcopy(self.read_clean_input)
        n_line = len(my_data)
        self.well_file = []
        for i in range(n_line):
            my_data[i] = my_data[i].strip("\n")
        for i in range(n_line):
            if my_data[i] == "WELLFILE":
                i = i + 1
                while str(my_data[i]) != "/":
                    self.well_file.append(str(my_data[i]).replace("'", ""))
                    i = i + 1
        if len(self.well_file) == 0:
            for i, ifile in enumerate(self.data_file):
                ecl_data = fp.clear_comments(ifile + ".DATA")
                ecl_data = ecl_data.readlines()
                for length in range(len(ecl_data)):
                    if "_advanced.wells" in ecl_data[length]:
                        well_file = ecl_data[length].replace("'", "")
                        well_file = well_file.replace(" ", "")
                        well_file = well_file.replace("\n", "")
                        well_file_split = well_file.split("/")
                        well_file_split = list(filter(None, well_file_split))
                        path_dict = self.relative_path(ifile + ".DATA")
                        if "$" in well_file_split[0]:
                            short = well_file_split[0].replace("$", "")
                            well_file_split[0] = path_dict[short]
                        well_file = "/".join(well_file_split)
                        self.well_file.append(well_file)
        if len(self.well_file) == 0:
            raise ValueError("Error : Well file is not specified")
        if self.n_file != len(self.well_file):
            raise ValueError("Error : Well file must be given for each Data file")

    def output_file_kw(self):
        """
        Read the content of the OUTPUTFILE keyword in the input file.

        Returns:
            Output file name
        """
        mydata = deepcopy(self.read_clean_input)
        n_line = len(mydata)
        self.output_file = ""
        for i in range(n_line):
            mydata[i] = mydata[i].strip("\n")
        for i in range(n_line):
            if mydata[i] == "OUTPUTFILE":
                if str(mydata[i + 1]) == "/":
                    my_warning = "Warning : Output file is not specified. "
                    my_warning += "WellBuilderPlot will not export the results."
                    print(my_warning)
                else:
                    self.output_file = str(mydata[i + 1])
                    self.output_file = self.output_file.replace("'", "")

    def information_kw(self):
        """
        Read the content of the INFORMATION keyword in the input file.

        Uses read_clean_input, a StringIO object of the input file.

        Returns:
            Content of the INFORMATION keyword.
        """

        completion_str = "WELL LATERAL TUBINGSEGMENT "
        completion_str += "DEVICESEGMENT ANNULUSSEGMENT DAYS\n"
        my_data = deepcopy(self.read_clean_input)
        n_line = len(my_data)
        for i in range(n_line):
            my_data[i] = my_data[i].strip("\n")

        for i in range(n_line):
            my_line = my_data[i]
            if my_line == "INFORMATION":
                break
        j = i + 1
        while my_data[j] != "/":
            completion_str = completion_str + "\n" + my_data[j]
            j = j + 1
        completion = pd.read_csv(StringIO(completion_str), sep=" ", index_col=False)
        completion["WELL"] = completion["WELL"].astype(str)
        completion["LATERAL"] = completion["LATERAL"].astype(np.int32)
        completion["TUBINGSEGMENT"] = completion["TUBINGSEGMENT"].astype(str)
        completion["DEVICESEGMENT"] = completion["DEVICESEGMENT"].astype(str)
        completion["ANNULUSSEGMENT"] = completion["ANNULUSSEGMENT"].astype(str)
        completion["DAYS"] = completion["DAYS"].astype(str)

        self.information = completion.copy(deep=True)

    def get_info_per_well(self, well, lateral):
        """
        Get information per well and lateral from INFORMATION keyword in the input file.

        Args:
            well (str): Well name
            lateral (int): Branch number

        Returns:
            List of tubing segments in the current well/branch\n
            List of device segments in the current well/branch\n
            List of annulus segments in the current well/branch\n
            Days from the start of simulation at which data will be obtained.

        Raises:
            ValueError: If the device segments are not supplied in intervals
                (from-to).
            ValueError: If the annulus segments are not supplied in intervals
                (from-to).
            ValueError: Unequal number of tubing and device segments. Complot
                only works for the 'cell' method in Completor.
        """

        info = self.information[self.information["WELL"] == well]
        info = info[info["LATERAL"] == lateral]
        # Tubing segments
        content = info["TUBINGSEGMENT"].iloc[0]
        if content == "1*":
            tubing_segment = np.zeros(1)
        else:
            content = content.split("-")
            if len(content) != 2:
                my_error = "Error : Tubing Segment must be defined "
                my_error += "by interval segment number e.g 1-200"
                print(my_error)
                sys.exit()
            else:
                start = int(content[0])
                end = int(content[1])
                tubing_segment = np.arange(start, end + 1, 1)
        # Device segments
        content = info["DEVICESEGMENT"].iloc[0]
        if content == "1*":
            device_segment = np.zeros(1)
        else:
            content = content.split("-")
            if len(content) == 2:
                start = int(content[0])
                end = int(content[1])
                device_segment = np.arange(start, end + 1, 1)
            else:
                my_error = "Error : Device Segment must be defined "
                my_error += "by interval segment number e.g 1-200"
                raise ValueError(my_error)
            # Check if the number of device segments are
            # equal to the number of tubing segments
            if len(tubing_segment) != len(device_segment):
                my_error = "Error : the number of device segments are "
                my_error += "not the same with the number of tubing segments."
                raise ValueError(my_error)
        # Annulus segment
        content = info["ANNULUSSEGMENT"].iloc[0]
        if content == "1*":
            annulus_segment = np.zeros(1)
        else:
            content = content.split("-")
            if len(content) == 2:
                start = int(content[0])
                end = int(content[1])
                annulus_segment = np.arange(start, end + 1, 1)
            else:
                my_error = "Error : Annulus Segment must be "
                my_error += "defined by interval segment number e.g 1-200"
                raise ValueError(my_error)
        # Days
        content = info["DAYS"].iloc[0]
        if content == "1*":
            my_warning = "Warning : Column DAYS is not supplied. "
            my_warning += "Selects the first time step by default."
            print(my_warning)
            my_days = np.zeros(1)
        else:
            my_days = np.asarray(content.split("-"))
            my_days = my_days.astype(np.float64)
        return tubing_segment, device_segment, annulus_segment, my_days

    def get_trajectory(self, well, tubing_segment):
        """
        Get the well trajectory from the DATA file WELSEGS keyword.

        Args:
            well (str): Well name
            tubing_segment (ndarray): List of tubing segments

        Returns:
            A DataFrame containing the TUBINGMD and TUBINGTVD columns of the\n
            WELSEGS DataFrame corresponding to the tubing_segment list of the\n
            current well.
        """

        for welsegs_i_well in self.welsegs_table:
            if welsegs_i_well.well == well:
                welsegs = welsegs_i_well.content.copy(deep=True)
                welsegs = welsegs[welsegs["TUBINGSEGMENT"].isin(tubing_segment)]
                welsegs = welsegs[["TUBINGMD", "TUBINGTVD"]]
                welsegs.sort_values(by=["TUBINGMD"], ascending=True, inplace=True)
                return welsegs

    def get_packer(self, well, annulus_segment):
        """
        Gets packer information for the annulus layer.

        Args:
            well (str): Well name
            annulus_segment (ndarray): List of annulus segments

        Returns:
            Packer information DataFrame\n
            Annulus information DataFrame\n
        """

        if len(annulus_segment) > 1:
            for welsegs_iwell in self.welsegs_table:
                if welsegs_iwell.well == well:
                    welsegs = welsegs_iwell.content.copy(deep=True)
                    welsegs = welsegs[welsegs["TUBINGSEGMENT"].isin(annulus_segment)]
                    packer_md = [welsegs["TUBINGMD"].iloc[0]]
                    packer_tvd = [welsegs["TUBINGTVD"].iloc[0]]
                    df_annulus_zones = pd.DataFrame()
                    df_annulus_zones["SEGMENT"] = welsegs["TUBINGSEGMENT"].values
                    df_annulus_zones["MD"] = welsegs["TUBINGMD"].values
                    annulus_zone = np.full(welsegs.shape[0], 1)
                    for i in range(1, welsegs.shape[0]):
                        if (
                            welsegs["TUBINGOUTLET"].iloc[i]
                            != welsegs["TUBINGSEGMENT"].iloc[i - 1]
                        ):
                            packer_md.append(welsegs["TUBINGMD"].iloc[i - 1])
                            packer_md.append(welsegs["TUBINGMD"].iloc[i])

                            packer_tvd.append(welsegs["TUBINGTVD"].iloc[i - 1])
                            packer_tvd.append(welsegs["TUBINGTVD"].iloc[i])
                            annulus_zone[i] = annulus_zone[i - 1] + 1
                        else:
                            annulus_zone[i] = annulus_zone[i - 1]
                        if i == welsegs.shape[0] - 1:
                            packer_md.append(welsegs["TUBINGMD"].iloc[i])
                            packer_tvd.append(welsegs["TUBINGTVD"].iloc[i])
                    df_annulus_zones["ANNULUS_ZONE"] = annulus_zone
                    df_annulus_zones["ANNULUS_ZONE"] = df_annulus_zones[
                        "ANNULUS_ZONE"
                    ].astype(np.int32)
                    df_packer = pd.DataFrame(
                        np.column_stack((packer_md, packer_tvd)),
                        columns=["PACKERMD", "PACKERTVD"],
                    )
                    return df_packer, df_annulus_zones
        else:
            return pd.DataFrame(), pd.DataFrame()

    def get_day_index(self, list_of_days):
        """
        Gets the day index or nearest day index by comparing the input file
        INFORMATION keyword day parameters with the simulation days from
        Eclipse.

        Args:
            list_of_days (ndarray): A list of days from the input file.

        Returns:
            List of day indices.
        """
        day_idx = np.full(len(list_of_days), -1)
        for i, day in enumerate(list_of_days):
            idx = np.argwhere(self.eclipse_days == day)
            idx = idx.reshape(idx.shape[0])
            if len(idx) > 0:
                day_idx[i] = idx[0]
            else:
                my_warning = f"Warning: No exact day is found in Eclipse for {day}"
                my_warning = my_warning + " . The program uses the closest day."
                print(my_warning)
                dif = abs(self.eclipse_days - day)
                idx = np.argsort(dif)
                idx = idx.reshape(idx.shape[0])
                day_idx[i] = idx[0]
        return day_idx

    def get_md(
        self, well, segment, lateral, section, device_interval=0.1, annulus_interval=0.1
    ):
        """
        Get the measured depth of the welsegs segments. Pairing the WELSEGS
        keyword with COMPSEGS.

        Args:
            well (str): Well name
            segment (ndarray): List of segments
            lateral (int): Lateral number
            section (str): Section name (tubing, device or annulus)
            device_interval (float): . Default to 0.1
            annulus_interval (float): . Default to 0.1

        Returns:
            DataFrame with well segment data, including the measured depth.
        """

        for welsegs_i_well in self.welsegs_table:
            if welsegs_i_well.well == well:
                welsegs = welsegs_i_well.content.copy(deep=True)
                welsegs = welsegs[["TUBINGSEGMENT", "TUBINGMD", "TUBINGID"]]
                welsegs["TUBINGID"] = welsegs["TUBINGID"].astype(np.float64)
                welsegs["WELL"] = well
                welsegs = welsegs[["WELL", "TUBINGSEGMENT", "TUBINGMD", "TUBINGID"]]
                columns = {
                    "TUBINGSEGMENT": "Segment",
                    "TUBINGMD": "MD",
                    "TUBINGID": "DIAMETER",
                }
                welsegs.rename(columns=columns, inplace=True)
                break
        welsegs = welsegs[welsegs["Segment"].isin(segment)]

        for compsegs_i_well in self.compsegs_table:
            if compsegs_i_well.well == well:
                compsegs = compsegs_i_well.content.copy(deep=True)
                compsegs = compsegs[["I", "J", "K", "STARTMD", "ENDMD"]]
                i_lateral = 0
                a_row = 0
                for idx in range(compsegs.shape[0]):
                    end_md_branch = compsegs["ENDMD"].iloc[idx]
                    if idx < compsegs.shape[0] - 3:
                        # Define a new lateral branch if the start MD
                        # of the three consecutive cells is less than
                        # the end MD of the last cell in the preivous
                        # lateral branch.
                        start_1 = compsegs["STARTMD"].iloc[idx + 1]
                        start_2 = compsegs["STARTMD"].iloc[idx + 2]
                        start_3 = compsegs["STARTMD"].iloc[idx + 3]
                        if (
                            (start_1 < end_md_branch)
                            and (start_2 < end_md_branch)
                            and (start_3 < end_md_branch)
                        ):
                            i_lateral = i_lateral + 1
                            zrow = idx
                            if i_lateral == lateral:
                                break
                            a_row = idx + 1
                    else:
                        i_lateral = i_lateral + 1
                        zrow = compsegs.shape[0] - 1
                        if i_lateral == lateral:
                            break
                compsegs = compsegs.loc[a_row : zrow + 1, :]
                compsegs["WELL"] = well
                compsegs = compsegs[["WELL", "I", "J", "K", "STARTMD", "ENDMD"]]
                break

        if section == "tubing":
            measured_depth = welsegs["MD"].values
        elif section == "device":
            measured_depth = welsegs["MD"].values - device_interval
        elif section == "annulus":
            measured_depth = welsegs["MD"].values - annulus_interval
        start_md = compsegs["STARTMD"].values
        end_md = compsegs["ENDMD"].values
        comp_i = compsegs["I"].values
        comp_j = compsegs["J"].values
        comp_k = compsegs["K"].values

        # Merge welsegs and compsegs
        my_start = np.zeros(len(measured_depth))
        my_end = np.zeros(len(measured_depth))
        my_i = np.full(len(measured_depth), -1)
        my_j = np.full(len(measured_depth), -1)
        my_k = np.full(len(measured_depth), -1)
        for i, imd in enumerate(measured_depth):
            idx = np.argwhere((start_md <= imd) & (imd <= end_md))
            idx = idx.reshape(idx.shape[0])
            if len(idx) > 0:
                idx = idx[0]
                my_start[i] = start_md[idx]
                my_end[i] = end_md[idx]
                my_i[i] = comp_i[idx]
                my_j[i] = comp_j[idx]
                my_k[i] = comp_k[idx]
            else:
                segment = str(welsegs["Segment"].iloc[i])
                raise ValueError(
                    f"Error : Segment {segment} is not" + " found inside grid cells"
                )
        welsegs["STARTMD"] = my_start
        welsegs["ENDMD"] = my_end
        welsegs["I"] = my_i
        welsegs["J"] = my_j
        welsegs["K"] = my_k

        compdat = self.compdat_table[self.compdat_table["WELL"] == well]
        compdat = compdat[["I", "J", "K", "CF", "KH"]]
        try:
            compdat["CF"] = compdat["CF"].astype(np.float64)
        except Exception:
            pass
        try:
            compdat["KH"] = compdat["KH"].astype(np.float64)
        except Exception:
            pass
        welsegs = pd.merge(
            welsegs,
            compdat,
            how="left",
            left_on=["I", "J", "K"],
            right_on=["I", "J", "K"],
        )
        return welsegs

    def get_well_profile(self, well):
        """
        Set up dataframe of Eclipse well summary keywords and extracts.

        Args:
            well (str): Well name

        Returns:
            DataFrame with Eclipse summary keywords and time series.
        """

        well_kw = ["WBHP", "WOPR", "WWPR", "WGPR", "WWCT", "WGOR"]
        self.df_well = pd.DataFrame()
        self.df_well["DAY"] = self.eclipse_days
        self.df_well["DATE"] = self.eclipse_dates
        for _, keyword in enumerate(well_kw):
            self.df_well[keyword] = self.eclipse.numpy_vector(keyword + ":" + well)
        self.df_well["WLPR"] = self.df_well["WOPR"] + self.df_well["WWPR"]

    def get_data(self, well, lateral):
        """
        Gets segment summary data.

        Args:
            well (str): Well name
            lateral (int): Lateral number

        Returns:
            DataFrame of segment summary data.
        """

        min_rate = 0.1
        self.list_keywords = ["SPR", "SPRD", "SOFR", "SWFR", "SGFRF"]
        self.kw_valid = []
        for keyword in self.list_keywords:
            try:
                prof = self.eclipse.numpy_vector(keyword + ":" + well + ":" + str(1))
                self.kw_valid.append(keyword)
            except Exception:
                print(f"Warning : {keyword} vector is not found in {well}")
        header = [
            "WELL",
            "SECTION",
            "DATE",
            "SEGMENT",
            "MD",
            "STARTMD",
            "ENDMD",
            "CF",
            "KH",
            "THICKNESS",
            "DIAMETER",
        ]

        # Device section
        n_device = len(self.device_segment)
        if n_device > 1:
            for i_x, idx in enumerate(self.my_days_idx):
                np_well = np.full(n_device, well)
                np_section = np.full(n_device, "Device")
                np_date = np.full(n_device, self.eclipse_dates[idx])
                np_segment = deepcopy(self.device_segment)
                welsegs = self.get_md(well, np_segment, lateral, section="device")
                np_md = welsegs["MD"].values
                np_start_md = welsegs["STARTMD"].values
                np_end_md = welsegs["ENDMD"].values
                np_cf = welsegs["CF"].values
                np_kh = welsegs["KH"].values
                np_thickness = np_end_md - np_start_md
                np_diameter = welsegs["DIAMETER"].values
                data_frame = np.column_stack(
                    (
                        np_well,
                        np_section,
                        np_date,
                        np_segment,
                        np_md,
                        np_start_md,
                        np_end_md,
                        np_cf,
                        np_kh,
                        np_thickness,
                        np_diameter,
                    )
                )
                data_frame = pd.DataFrame(data_frame, columns=header)

                for keyword in self.kw_valid:
                    if (
                        keyword == "SPR"
                        or keyword == "SPRD"
                        or keyword == "SGFRF"
                        or keyword == "SOFR"
                        or keyword == "SWFR"
                    ):
                        value = np.zeros(len(np_segment))
                        for i, seg in enumerate(np_segment):
                            prof = self.eclipse.numpy_vector(
                                keyword + ":" + well + ":" + str(seg)
                            )
                            value[i] = prof[idx]
                        data_frame[keyword] = value

                try:
                    swct = np.where(
                        (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"])) < min_rate,
                        0.0,
                        abs(data_frame["SWFR"])
                        / (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"]) + 0.00001),
                    )
                    data_frame["SWCT"] = swct
                except Exception:
                    pass

                try:
                    data_frame["SGOR"] = abs(data_frame["SGFRF"]) / (
                        abs(data_frame["SOFR"]) + 0.00001
                    )
                except Exception:
                    pass

                if i_x == 0:
                    df_all = data_frame.copy(deep=True)
                if i_x > 0:
                    df_all = pd.concat([df_all, data_frame])

        # Tubing section
        n_tubing = len(self.tubing_segment)
        for i_x, idx in enumerate(self.my_days_idx):
            np_well = np.full(n_tubing, well)
            np_section = np.full(n_tubing, "Tubing")
            np_date = np.full(n_tubing, self.eclipse_dates[idx])
            np_segment = deepcopy(self.tubing_segment)

            welsegs = self.get_md(well, np_segment, lateral, section="tubing")

            np_md = welsegs["MD"].values
            np_start_md = welsegs["STARTMD"].values
            np_end_md = welsegs["ENDMD"].values
            np_cf = welsegs["CF"].values
            np_kh = welsegs["KH"].values

            np_thickness = np_end_md - np_start_md
            np_diameter = welsegs["DIAMETER"].values
            data_frame = np.column_stack(
                (
                    np_well,
                    np_section,
                    np_date,
                    np_segment,
                    np_md,
                    np_start_md,
                    np_end_md,
                    np_cf,
                    np_kh,
                    np_thickness,
                    np_diameter,
                )
            )
            data_frame = pd.DataFrame(data_frame, columns=header)
            for keyword in self.kw_valid:
                value = np.zeros(len(np_segment))
                if keyword != "SGFRF":
                    for i, seg in enumerate(np_segment):
                        prof = self.eclipse.numpy_vector(
                            keyword + ":" + well + ":" + str(seg)
                        )
                        value[i] = prof[idx]
                    data_frame[keyword] = value
                else:
                    df_related = df_all[df_all["DATE"] == self.eclipse_dates[idx]]
                    df_related = df_related[df_related["SECTION"] == "Device"]
                    rate_inflow = df_related[keyword].values
                    for isq in range(len(rate_inflow) - 1, -1, -1):
                        if isq == len(rate_inflow) - 1:
                            value[isq] = rate_inflow[isq]
                        else:
                            value[isq] = value[isq + 1] + rate_inflow[isq]
                    data_frame[keyword] = value
            try:
                swct = np.where(
                    (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"])) < min_rate,
                    0.0,
                    abs(data_frame["SWFR"])
                    / (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"]) + 0.00001),
                )
                data_frame["SWCT"] = swct
            except Exception:
                pass
            try:
                data_frame["SGOR"] = abs(data_frame["SGFRF"]) / (
                    abs(data_frame["SOFR"]) + 0.00001
                )
            except Exception:
                pass

            df_all = pd.concat([df_all, data_frame])

        # Annulus section
        n_annulus = len(self.annulus_segment)
        if n_annulus > 1:
            for i_x, idx in enumerate(self.my_days_idx):
                np_well = np.full(n_annulus, well)
                np_section = np.full(n_annulus, "Annulus")
                np_date = np.full(n_annulus, self.eclipse_dates[idx])
                np_segment = deepcopy(self.annulus_segment)
                welsegs = self.get_md(well, np_segment, lateral, section="annulus")
                np_md = welsegs["MD"].values
                np_start_md = welsegs["STARTMD"].values
                np_end_md = welsegs["ENDMD"].values
                np_cf = welsegs["CF"].values
                np_kh = welsegs["KH"].values
                np_thickness = np_end_md - np_start_md
                np_diameter = welsegs["DIAMETER"].values
                data_frame = np.column_stack(
                    (
                        np_well,
                        np_section,
                        np_date,
                        np_segment,
                        np_md,
                        np_start_md,
                        np_end_md,
                        np_cf,
                        np_kh,
                        np_thickness,
                        np_diameter,
                    )
                )
                data_frame = pd.DataFrame(data_frame, columns=header)
                for keyword in self.kw_valid:
                    value = np.zeros(len(np_segment))
                    for i, seg in enumerate(np_segment):
                        prof = self.eclipse.numpy_vector(
                            keyword + ":" + well + ":" + str(seg)
                        )
                        value[i] = prof[idx]
                    data_frame[keyword] = value
                try:
                    swct = np.where(
                        (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"])) < min_rate,
                        0.0,
                        abs(data_frame["SWFR"])
                        / (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"]) + 0.00001),
                    )
                    data_frame["SWCT"] = swct
                except Exception:
                    pass

                try:
                    data_frame["SGOR"] = abs(data_frame["SGFRF"]) / (
                        abs(data_frame["SOFR"]) + 0.00001
                    )
                except Exception:
                    pass

                df_all = pd.concat([df_all, data_frame])

        df_all["SEGMENT"] = df_all["SEGMENT"].astype(np.int32)
        df_all["MD"] = df_all["MD"].astype(np.float64)
        df_all["STARTMD"] = df_all["STARTMD"].astype(np.float64)
        df_all["ENDMD"] = df_all["ENDMD"].astype(np.float64)

        try:
            df_all["CF"] = df_all["CF"].astype(np.float64)
        except Exception:
            df_all["CF"] = 1.0e-10

        try:
            df_all["KH"] = df_all["KH"].astype(np.float64)
        except Exception:
            df_all["KH"] = 1.0e-10

        df_all["THICKNESS"] = df_all["THICKNESS"].astype(np.float64)
        df_all["DIAMETER"] = df_all["DIAMETER"].astype(np.float64)

        # Reservoir section
        for i_x, idx in enumerate(self.my_days_idx):
            np_well = np.full(n_device, well)
            np_section = np.full(n_device, "Reservoir")
            np_date = np.full(n_device, self.eclipse_dates[idx])
            np_segment = deepcopy(self.tubing_segment)

            welsegs = self.get_md(well, np_segment, lateral, section="tubing")

            np_md = welsegs["MD"].values
            np_start_md = welsegs["STARTMD"].values
            np_end_md = welsegs["ENDMD"].values
            np_cf = welsegs["CF"].values
            np_kh = welsegs["KH"].values

            np_thickness = np_end_md - np_start_md
            np_diameter = welsegs["DIAMETER"].values
            data_frame = np.column_stack(
                (
                    np_well,
                    np_section,
                    np_date,
                    np_segment,
                    np_md,
                    np_start_md,
                    np_end_md,
                    np_cf,
                    np_kh,
                    np_thickness,
                    np_diameter,
                )
            )
            data_frame = pd.DataFrame(data_frame, columns=header)
            for keyword in self.kw_valid:
                if keyword == "SPR" or keyword == "SPRD":
                    data_frame[keyword] = 0.0
                elif keyword == "SOFR" or keyword == "SWFR" or keyword == "SGFRF":
                    if n_annulus == 1:
                        # meaning only tubing segments are created
                        # in the Eclipse case or there are device
                        # segments but no annulus segments are created
                        df_related = df_all[df_all["DATE"] == self.eclipse_dates[idx]]
                        df_related = df_related[df_related["SECTION"] == "Tubing"]
                        rate_inflow = df_related[keyword].values
                        rate_upstream = rate_inflow[1:]
                        rate_upstream = np.insert(
                            rate_upstream, len(rate_upstream), 0.0
                        )
                        data_frame[keyword] = rate_inflow - rate_upstream
                    else:
                        df_device = df_all[df_all["DATE"] == self.eclipse_dates[idx]]
                        df_device = df_device[df_device["SECTION"] == "Device"]
                        df_device = df_device[["MD", keyword]]
                        df_device.rename(
                            columns={keyword: "DEVICE_" + keyword}, inplace=True
                        )

                        df_annulus = df_all[df_all["DATE"] == self.eclipse_dates[idx]]
                        df_annulus = df_annulus[df_annulus["SECTION"] == "Annulus"]
                        df_annulus = df_annulus[["MD", keyword]]
                        df_annulus.rename(
                            columns={keyword: "ANNULUS_" + keyword}, inplace=True
                        )
                        df_annulus = pd.merge(
                            df_annulus,
                            self.df_annulus_zone,
                            how="left",
                            left_on="MD",
                            right_on="MD",
                        )
                        df_annulus["MD2"] = df_annulus["MD"].values
                        df_merge = pd.merge_asof(
                            df_device, df_annulus, on="MD", direction="forward"
                        )
                        df_merge.fillna(0, inplace=True)
                        annulus_rate = np.where(
                            (df_merge["MD"].values < (df_merge["MD2"].values - 0.1)),
                            0.0,
                            df_merge["ANNULUS_" + keyword].values,
                        )
                        annulus_zone = np.where(
                            (df_merge["MD"].values < (df_merge["MD2"].values - 0.1)),
                            0,
                            df_merge["ANNULUS_ZONE"].values,
                        )
                        df_merge["ANNULUS_" + keyword] = annulus_rate
                        df_merge["ANNULUS_ZONE"] = annulus_zone
                        annulus_zone = df_merge["ANNULUS_ZONE"].unique()
                        for i_z, izone in enumerate(annulus_zone):
                            df_temp = df_merge[df_merge["ANNULUS_ZONE"] == izone]
                            if izone == 0:
                                measured_depth = df_temp["MD"].values
                                xrate = df_temp["DEVICE_" + keyword].values
                            else:
                                rate_device = df_temp["DEVICE_" + keyword].values
                                rate_annulus_out = df_temp["ANNULUS_" + keyword].values
                                rate_annulus_in = rate_annulus_out[1:]
                                rate_annulus_in = np.insert(
                                    rate_annulus_in, len(rate_annulus_in), 0.0
                                )
                                xrate = rate_annulus_out - rate_annulus_in + rate_device
                                xrate[0] = -rate_annulus_in[0] + rate_device[0]
                                measured_depth = df_temp["MD"].values
                            df_reservoir_each = pd.DataFrame()
                            df_reservoir_each["MD"] = measured_depth
                            df_reservoir_each[keyword] = xrate
                            if i_z == 0:
                                df_reservoir = df_reservoir_each.copy(deep=True)
                            else:
                                df_reservoir = pd.concat(
                                    [df_reservoir, df_reservoir_each]
                                )
                        # sort based on md
                        df_reservoir.sort_values(by=["MD"], inplace=True)
                        df_reservoir["MD"] = df_reservoir["MD"].astype(np.float64)
                        data_frame["MD"] = data_frame["MD"].astype(np.float64)
                        df_merge = pd.merge_asof(
                            data_frame, df_reservoir, on="MD", direction="nearest"
                        )
                        data_frame[keyword] = df_merge[keyword].values

            try:
                swct = np.where(
                    (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"])) < min_rate,
                    0.0,
                    abs(data_frame["SWFR"])
                    / (abs(data_frame["SWFR"]) + abs(data_frame["SOFR"]) + 0.00001),
                )
                data_frame["SWCT"] = swct
            except Exception:
                pass
            try:
                data_frame["SGOR"] = abs(data_frame["SGFRF"]) / (
                    abs(data_frame["SOFR"]) + 0.00001
                )
            except Exception:
                pass
            df_all = pd.concat([df_all, data_frame])
        # 0.1 m is 10 cm
        df_all["AREA_10CM"] = PI * df_all["DIAMETER"].values * 0.1
        df_all["AREA_10CM"] = df_all["AREA_10CM"].astype(np.float64)
        try:
            df_all["OIL_VELOCITY"] = df_all["SOFR"] / df_all["AREA_10CM"]
            df_all["OIL_VELOCITY_M/S_10CM"] = df_all["OIL_VELOCITY"] / (24 * 60 * 60)
            df_all["SOFR_M"] = df_all["SOFR"] / (df_all["THICKNESS"] + 0.000001)

            df_all["OIL_VELOCITY"] = df_all["OIL_VELOCITY"].astype(np.float64)
            df_all["OIL_VELOCITY_M/S_10CM"] = df_all["OIL_VELOCITY_M/S_10CM"].astype(
                np.float64
            )
            df_all["SOFR_M"] = df_all["SOFR_M"].astype(np.float64)
        except Exception:
            pass
        try:
            df_all["WATER_VELOCITY"] = df_all["SWFR"] / df_all["AREA_10CM"]
            df_all["WATER_VELOCITY_M/S_10CM"] = df_all["WATER_VELOCITY"] / (
                24 * 60 * 60
            )
            df_all["SWFR_M"] = df_all["SWFR"] / (df_all["THICKNESS"] + 0.000001)
            df_all["WATER_VELOCITY"] = df_all["WATER_VELOCITY"].astype(np.float64)
            df_all["WATER_VELOCITY_M/S_10CM"] = df_all[
                "WATER_VELOCITY_M/S_10CM"
            ].astype(np.float64)
            df_all["SWFR_M"] = df_all["SWFR_M"].astype(np.float64)
        except Exception:
            pass
        try:
            df_all["GAS_VELOCITY"] = df_all["SGFRF"] / df_all["AREA_10CM"]
            df_all["GAS_VELOCITY_M/S_10CM"] = df_all["GAS_VELOCITY"] / (24 * 60 * 60)
            df_all["SGFRF_M"] = df_all["SGFRF"] / (df_all["THICKNESS"] + 0.000001)
            df_all["GAS_VELOCITY"] = df_all["GAS_VELOCITY"].astype(np.float64)
            df_all["GAS_VELOCITY_M/S_10CM"] = df_all["GAS_VELOCITY_M/S_10CM"].astype(
                np.float64
            )
            df_all["SGFRF_M"] = df_all["SGFRF_M"].astype(np.float64)
        except Exception:
            pass
        df_all["SEGMENT"] = df_all["SEGMENT"].astype(np.int32)
        df_all["MD"] = df_all["MD"].astype(np.float64)
        df_all["STARTMD"] = df_all["STARTMD"].astype(np.float64)
        df_all["ENDMD"] = df_all["ENDMD"].astype(np.float64)
        try:
            df_all["CF"] = df_all["CF"].astype(np.float64)
        except Exception:
            df_all["CF"] = 1.0e-10
        try:
            df_all["KH"] = df_all["KH"].astype(np.float64)
        except Exception:
            df_all["KH"] = 1.0e-10
        df_all["THICKNESS"] = df_all["THICKNESS"].astype(np.float64)
        df_all["DIAMETER"] = df_all["DIAMETER"].astype(np.float64)

        self.df_output = df_all.copy(deep=True)

    def plot_pressure(self, sub_pr, date, date_idx, well, lateral, case=""):
        """
        Plot the tubing and device layer pressures along the well bore.

        Set labels.

        Args:
            sub_pr (AxesSubplot): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            well (str): Well name
            lateral (int): Lateral index
            case (str): Case identifier

        Returns:
            Tubing and device layer pressure plots.
        """
        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")

        if date_idx == 0:
            tub_curve = "r-"
            ann_curve = "b-"
        else:
            tub_curve = "r:"
            ann_curve = "b:"

        try:
            # tubing
            if self.df_tubing.shape[0] > 0:
                sub_pr.plot(
                    self.df_tubing["MD"].values,
                    self.df_tubing["SPR"].values,
                    tub_curve,
                    label=case + " " + "Tubing : " + date_label,
                )
            # device
            if self.df_device.shape[0] > 0:
                sub_pr.plot(
                    self.df_device["MD"].values,
                    self.df_device["SPR"].values,
                    ann_curve,
                    label=case + " " + "Annulus : " + date_label,
                )
        except Exception:
            pass
        format_subplot(
            sub_pr,
            well + " - Branch " + str(lateral),
            "mMD",
            "Pressure, Bar",
            legend_location="right",
        )

    def plot_cumulative(self, sub_pr_owg, date, date_idx, df_packer, case=""):
        """
        Plot cumulative production along the tubing and annulus layers.

        Set labels, colors and styles.

        Args:
            sub_pr_owg (object): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            df_packer (pd.DataFrame): DataFrame with packer information.
            case (str): Case identifier

        Returns:
            Tubing and annulus layer cumulative production plots.
        """
        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")
        parameter = ["SOFR", "SWFR", "SGFRF"]
        title = ["Cum Qo, sm3/d", "Cum Qw, sm3/d", "Cum Qg, sm3/d"]
        if date_idx == 0:
            tub_curve = ["g-", "b-", "r-"]
            ann_curve = ["g--", "b--", "r--"]
            face_color = ["green", "blue", "red"]
        else:
            tub_curve = ["g-.", "b-.", "r-."]
            ann_curve = ["g:", "b:", "r:"]

        for idx, sub_pr in enumerate(sub_pr_owg):
            idx_param = parameter[idx]
            try:
                # Annulus
                if self.df_annulus.shape[0] > 0:
                    x = self.df_annulus["MD"].values
                    y = self.df_annulus[idx_param].values
                    df_xy = pd.DataFrame(np.column_stack((x, y)), columns=["X", "Y"])
                    df_xy_add = pd.DataFrame()
                    df_xy_add["X"] = df_packer["PACKERMD"].values
                    df_xy_add["Y"] = 0.0
                    df_xy = pd.concat([df_xy, df_xy_add])
                    df_xy.sort_values(by=["X", "Y"], inplace=True)
                    x = df_xy["X"].values
                    y = df_xy["Y"].values
                    min_md = min(self.df_tubing["MD"].values)
                    max_md = max(self.df_tubing["MD"].values)
                    x = np.insert(x, 0, min_md)
                    x = np.insert(x, len(x), max_md)
                    y = np.insert(y, 0, 0.0)
                    y = np.insert(y, len(y), 0.0)
                    sub_pr.plot(
                        x, y, ann_curve[idx], label=case + " " + "Annulus : " + date_label
                    )
                    sub_pr.fill_between(x, 0, y, facecolor=face_color[idx], alpha=0.5)
                # tubing
                if self.df_tubing.shape[0] > 0:
                    sub_pr.plot(
                        self.df_tubing["MD"].values,
                        self.df_tubing[idx_param].values,
                        tub_curve[idx],
                        label=case + " " + "Tubing : " + date_label,
                    )
            except Exception:
                pass
            format_subplot(sub_pr, "", "mMD", title[idx], legend_location="right")

    def plot_velocity(self, sub_pr_owg, date, date_idx, case=""):
        """
        Plot fluid velocity in the annulus layer and the 1 m/s erosional limit.

        Set labels, colors and styles.

        Args:
            sub_pr_owg (object): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            case (str): Case identifier

        Returns:
            Annulus layer velocity plot.
        """
        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")
        parameter = [
            "OIL_VELOCITY_M/S_10CM",
            "WATER_VELOCITY_M/S_10CM",
            "GAS_VELOCITY_M/S_10CM",
        ]
        if date_idx == 0:
            ann_curve = ["g--", "b--", "r--"]
        else:
            ann_curve = ["g:", "b:", "r:"]

        for idx, sub_pr in enumerate(sub_pr_owg):
            idx_param = parameter[idx]
            if idx == 0:
                # plot boundary 1m/s
                sub_pr.plot(
                    self.df_annulus["MD"].values,
                    np.full(self.df_annulus["MD"].values.shape[0], 1.0),
                    "k-",
                    label="max 1 m/s",
                )
            try:
                # Annulus
                if self.df_annulus.shape[0] > 0:
                    sub_pr.plot(
                        self.df_annulus["MD"].values,
                        self.df_annulus[idx_param].values,
                        ann_curve[idx],
                        label=case + " " + "Annulus : " + date_label,
                    )
            except Exception:
                pass
            format_subplot(sub_pr, "", "mMD", "Vel.m/d@STD", legend_location="right")

    def plot_inflow(self, sub_pr_owg, date, date_idx, case=""):
        """
        Plot inflow from the reservoir to the well. Sets labels, colors and styles.

        Args:
            sub_pr_owg (object): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            case (str): Case identifier

        Returns:
            Inflow plot.
        """
        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")
        parameter = ["SOFR", "SWFR", "SGFRF"]
        title = ["Qo, sm3/d", "Qw, sm3/d", "Qg, sm3/d"]

        if date_idx == 0:
            tub_curve = ["g-", "b-", "r-"]
            ann_curve = ["g--", "b--", "r--"]
        else:
            tub_curve = ["g-.", "b-.", "r-."]
            ann_curve = ["g:", "b:", "r:"]
        for idx, sub_pr in enumerate(sub_pr_owg):
            idx_param = parameter[idx]
            try:
                # Reservoir
                if self.df_reservoir.shape[0] > 0:
                    sub_pr.plot(
                        self.df_reservoir["MD"].values,
                        self.df_reservoir[idx_param].values,
                        ann_curve[idx],
                        label=case + " " + "Reservoir : " + date_label,
                    )
                # device
                if self.df_device.shape[0] > 0:
                    sub_pr.plot(
                        self.df_device["MD"].values,
                        self.df_device[idx_param].values,
                        tub_curve[idx],
                        label=case + " " + "Device : " + date_label,
                    )

            except Exception:
                pass
            format_subplot(sub_pr, "", "mMD", title[idx], legend_location="right")

    def plot_inflow_per_meter(self, sub_pr_owg, date, date_idx, case=""):
        """
        Create the plots showing production rate pr meter. Sets labels, colors
        and legends.

        Args:
            sub_pr_owg (object): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            case (str): Case identifier

        Returns:
            Production rate pr meter plots.
        """
        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")
        parameter = ["SOFR_M", "SWFR_M", "SGFRF_M"]
        title = ["Qo, sm3/d/m", "Qw, sm3/d/m", "Qg, sm3/d/m"]
        if date_idx == 0:
            tub_curve = ["g-", "b-", "r-"]
        else:
            tub_curve = ["g-.", "b-.", "r-."]
        for idx, sub_pr in enumerate(sub_pr_owg):
            idx_param = parameter[idx]
            try:
                # Reservoir
                if self.df_reservoir.shape[0] > 0:
                    sub_pr.plot(
                        self.df_reservoir["MD"].values,
                        self.df_reservoir[idx_param].values,
                        tub_curve[idx],
                        label=case + " " + "Reservoir : " + date_label,
                    )
            except Exception:
                pass
            format_subplot(sub_pr, "", "mMD", title[idx], legend_location="right")

    def plot_fraction(self, sub_pr_owg, date, date_idx, case=""):
        """
        Plot water cut and gor along the device and annulus layers.

        Args:
            sub_pr_owg (object): AxesSubPlot object
            date (object): Datetime date object.
            date_idx (int): Date index
            case (str): Case identifier

        Returns:
            Plots of water cut and gor.
        """

        if date == "":
            date_label = ""
        else:
            time_step = pd.to_datetime(str(date))
            date_label = time_step.strftime("%Y-%m-%d")
        parameter = ["SWCT", "SGOR"]
        title = ["WCT", "GOR"]
        if date_idx == 0:
            tub_curve = ["b-", "r-"]
            ann_curve = ["b--", "r--"]
        else:
            tub_curve = ["b-.", "r-."]
            ann_curve = ["b:", "r:"]
        for i, sub_pr in enumerate(sub_pr_owg):
            iparam = parameter[i]
            try:
                # Reservoir
                if self.df_reservoir.shape[0] > 0:
                    sub_pr.plot(
                        self.df_reservoir["MD"].values,
                        self.df_reservoir[iparam].values,
                        ann_curve[i],
                        label=case + " " + "Reservoir : " + date_label,
                    )
                # device
                if self.df_device.shape[0] > 0:
                    sub_pr.plot(
                        self.df_device["MD"].values,
                        self.df_device[iparam].values,
                        tub_curve[i],
                        label=case + " " + "Device : " + date_label,
                    )
            except Exception:
                pass

            format_subplot(sub_pr, "", "mMD", title[i], legend_location="right")

    def plot_well_profile(self, figure, well, case=""):
        """
        Plot well profiles.

        Args:
            figure (Figure): A matplotlib figure object.
            well (str): Well name
            case (str): Case identifier

        Returns:
            Plots profiles along the well bore.
        """
        figure.suptitle(well)
        update_fonts(size=8)
        plt_wbhp = figure.add_subplot(2, 2, 1)
        plt_ow = figure.add_subplot(2, 2, 2)
        plt_gas = figure.add_subplot(2, 2, 3)
        plt_gas_twin = plt_gas.twinx()
        plt_wct = figure.add_subplot(2, 2, 4)

        plt_wbhp.plot(
            self.df_well["DAY"].values,
            self.df_well["WBHP"].values,
            "r-",
            label=case + " " + "BHP",
        )
        plt_ow.plot(
            self.df_well["DAY"].values,
            self.df_well["WOPR"].values,
            "g-",
            label=case + " " + "Qo",
        )
        plt_ow.plot(
            self.df_well["DAY"].values,
            self.df_well["WWPR"].values,
            "b-",
            label=case + " " + "Qw",
        )
        plt_ow.plot(
            self.df_well["DAY"].values,
            self.df_well["WLPR"].values,
            "k-",
            label=case + " " + "Ql",
        )

        plt_gas.plot(
            self.df_well["DAY"].values,
            self.df_well["WGPR"].values,
            "r-",
            label=case + " " + "Qg",
        )
        plt_gas.plot(np.nan, "r:", label="GOR")
        plt_gas_twin.plot(
            self.df_well["DAY"].values,
            self.df_well["WGOR"].values,
            "r:",
            label=case + " " + "GOR",
        )
        plt_wct.plot(
            self.df_well["DAY"].values,
            self.df_well["WWCT"].values,
            "b-",
            label=case + " " + "Water Cut",
        )

        plt_wbhp.set_ylabel("BHP, Bar")
        plt_ow.set_ylabel("Rate, sm3/d")
        plt_gas.set_ylabel("Rate, sm3/d")
        plt_gas_twin.set_ylabel("GOR, sm3/sm3")
        plt_wct.set_ylabel("Wct")

        sub_pr_well = [plt_wbhp, plt_ow, plt_gas, plt_wct]
        for sub_pr in sub_pr_well:
            sub_pr.legend(
                bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
                loc=3,
                ncol=2,
                mode="expand",
                borderaxespad=0,
            )
            sub_pr.tick_params(labelbottom=True)
            sub_pr.set_xlabel("Day")
            sub_pr.minorticks_on()
            sub_pr.grid(which="both", linestyle=":", linewidth=0.5, color="grey")
            sub_pr.tick_params(which="both", direction="in")

        figure.subplots_adjust(hspace=0.3, wspace=0.3)

    def arrange_subplots(self, figure):
        """
        Set the horizontal spacing between subplots.

        Args:
            figure (object): matplotlib figure object.

        Returns:
            Figure with horizontal spacing adjusted by 0.3
        """
        figure.subplots_adjust(hspace=0.3)

    def plot_trajectory(self, sub_pr_trajectory, trajectory, df_packer, case=""):
        """
        Plot the well trajectory.

        Args:
            sub_pr_trajectory (object): AxesSubPlot object
            trajectory (pd.DataFrame): TVD vs MD dataframe
            df_packer (pd.DataFrame): Packer dataframe
            case (str): Case name

        Returns:
            Trajectory plot with connection factor is exists. Add packer information.
        """

        for sub_pr in sub_pr_trajectory:
            sub_pr_twin = sub_pr.twinx()
            # plot trajectory
            sub_pr.plot(
                trajectory["TUBINGMD"].values,
                trajectory["TUBINGTVD"].values,
                "k-",
                label=" " + case,
            )
            min_tvd = min(trajectory["TUBINGTVD"].values)
            max_tvd = max(trajectory["TUBINGTVD"].values)
            interval = 0.1 * (max_tvd - min_tvd)
            # plot connection factor / transmissibility factor
            sub_pr_twin.plot(
                self.df_tubing["MD"].values,
                self.df_tubing["CF"].values,
                ".-",
                label=" ",
            )
            # plot packer
            if df_packer.shape[0] > 0:
                n_annulus_zones = int(df_packer.shape[0] / 2)
                for ip in range(n_annulus_zones):
                    start = df_packer["PACKERMD"].iloc[(ip * 2)] - 0.3
                    end = df_packer["PACKERMD"].iloc[(ip * 2) + 1]
                    this_zone_trajectory = trajectory[
                        (trajectory["TUBINGMD"] >= start)
                        & (trajectory["TUBINGMD"] <= end)
                    ]
                    sub_pr.scatter(
                        df_packer["PACKERMD"].values, df_packer["PACKERTVD"].values
                    )
                    sub_pr.fill_between(
                        this_zone_trajectory["TUBINGMD"].values,
                        this_zone_trajectory["TUBINGTVD"].values - interval,
                        this_zone_trajectory["TUBINGTVD"].values + interval,
                        facecolor="green",
                        alpha=0.2,
                    )
            format_subplot(sub_pr, "", "mMD", "mTVD")
            format_subplot(sub_pr_twin, "", "mMD", "CF")
            sub_pr.invert_yaxis()
            sub_pr.get_legend().remove()
            sub_pr_twin.get_legend().remove()

    def main(self):
        """
        The main function for complot.
        """
        for iw in range(self.information.shape[0]):
            # create new figures
            fig_1 = plt.figure()
            fig_2 = plt.figure()
            fig_3 = plt.figure()
            fig_4 = plt.figure()
            fig_5 = plt.figure()

            self.arrange_subplots(fig_1)
            self.arrange_subplots(fig_2)
            self.arrange_subplots(fig_3)
            self.arrange_subplots(fig_4)

            n, c = 5, 1
            update_fonts(size=8)
            sub_well_1 = fig_1.add_subplot(n, c, 5)
            sub_pr_1 = fig_1.add_subplot(n, c, 1, sharex=sub_well_1)
            sub_qo_cum = fig_1.add_subplot(n, c, 2, sharex=sub_well_1)
            sub_qw_cum = fig_1.add_subplot(n, c, 3, sharex=sub_well_1)
            sub_qg_cum = fig_1.add_subplot(n, c, 4, sharex=sub_well_1)

            sub_well_2 = fig_2.add_subplot(n, c, 5, sharex=sub_well_1)
            sub_pr_2 = fig_2.add_subplot(n, c, 1, sharex=sub_well_1)
            sub_qo_inflow = fig_2.add_subplot(n, c, 2, sharex=sub_well_1)
            sub_qw_inflow = fig_2.add_subplot(n, c, 3, sharex=sub_well_1)
            sub_qg_inflow = fig_2.add_subplot(n, c, 4, sharex=sub_well_1)

            sub_well_3 = fig_3.add_subplot(n, c, n, sharex=sub_well_1)
            sub_pr_3 = fig_3.add_subplot(n, c, 1, sharex=sub_well_1)
            sub_wct = fig_3.add_subplot(n, c, 2, sharex=sub_well_1)
            sub_gor = fig_3.add_subplot(n, c, 3, sharex=sub_well_1)
            sub_velocity = fig_3.add_subplot(n, c, 4, sharex=sub_well_1)

            sub_well_4 = fig_4.add_subplot(n, c, n, sharex=sub_well_1)
            sub_pr_4 = fig_4.add_subplot(n, c, 1, sharex=sub_well_1)
            sub_qo_perm = fig_4.add_subplot(n, c, 2, sharex=sub_well_1)
            sub_qw_perm = fig_4.add_subplot(n, c, 3, sharex=sub_well_1)
            sub_qg_perm = fig_4.add_subplot(n, c, 4, sharex=sub_well_1)
            for ifi in range(self.n_file):
                if self.n_file > 1:
                    case = self.case_name[ifi]
                else:
                    case = ""
                # Read Eclipse File
                self.read_data_file(self.data_file[ifi])
                # Read Well File
                self.read_well_file(self.well_file[ifi])
                # get information about the well name and the lateral number
                well = self.information["WELL"].iloc[iw]
                lateral = self.information["LATERAL"].iloc[iw]
                # read INFORMATION keyword and get information about the
                #  segment numbering in different layers and the day
                # to display
                (
                    self.tubing_segment,
                    self.device_segment,
                    self.annulus_segment,
                    self.my_days,
                ) = self.get_info_per_well(well, lateral)
                # find the index of the given day in the eclipse report
                self.my_days_idx = self.get_day_index(self.my_days)
                # get the well trajectory
                trajectory = self.get_trajectory(well, self.tubing_segment)
                # get packer location
                df_packer, self.df_annulus_zone = self.get_packer(
                    well, self.annulus_segment
                )
                # get the segment production profiles
                self.get_data(well, lateral)
                # get the well production profiles
                self.get_well_profile(well)
                # if the user wants to save the output file then
                # combine the existing report with the previous reports
                if iw == 0:
                    df_export = self.df_output.copy(deep=True)
                else:
                    df_export = pd.concat([df_export, self.df_output])
                self.plot_well_profile(fig_5, well)
                my_dates = self.df_output["DATE"].unique()
                if self.n_file > 1:
                    my_dates = my_dates[0:1]
                # plot pressure along the annulus and the tubing
                for date_idx, date in enumerate(my_dates):
                    df_this_date = self.df_output[self.df_output["DATE"] == date]
                    self.df_tubing = df_this_date[df_this_date["SECTION"] == "Tubing"]
                    self.df_device = df_this_date[df_this_date["SECTION"] == "Device"]
                    self.df_annulus = df_this_date[df_this_date["SECTION"] == "Annulus"]
                    self.df_reservoir = df_this_date[
                        df_this_date["SECTION"] == "Reservoir"
                    ]
                    if self.n_file > 1:
                        date = ""
                        date_idx = ifi
                    self.plot_pressure(sub_pr_1, date, date_idx, well, lateral, case=case)
                    self.plot_cumulative(
                        [sub_qo_cum, sub_qw_cum, sub_qg_cum],
                        date,
                        date_idx,
                        df_packer,
                        case=case,
                    )
                    self.plot_pressure(sub_pr_2, date, date_idx, well, lateral, case=case)
                    self.plot_inflow(
                        [sub_qo_inflow, sub_qw_inflow, sub_qg_inflow],
                        date,
                        date_idx,
                        case=case,
                    )
                    self.plot_pressure(sub_pr_4, date, date_idx, well, lateral, case=case)
                    self.plot_inflow_per_meter(
                        [sub_qo_perm, sub_qw_perm, sub_qg_perm], date, date_idx, case=case
                    )
                    self.plot_pressure(sub_pr_3, date, date_idx, well, lateral, case=case)
                    self.plot_fraction([sub_wct, sub_gor], date, date_idx, case=case)
                    self.plot_velocity([sub_velocity] * 3, date, date_idx, case=case)
                    if date_idx == 0:
                        self.plot_trajectory(
                            [sub_well_1, sub_well_2, sub_well_3, sub_well_4],
                            trajectory,
                            df_packer,
                            case=case,
                        )
        if self.output_file != "":
            df_export.to_csv(self.output_file, sep=";", index=False)


if __name__ == "__main__":
    arg = sys.argv[1]
    if arg == "-i":
        input_file = sys.argv[2]
        print("-----------------------------------------------------------")
        print("Running complot .......")
        mplot = SegmentPlot(input_file)
        if "-day" in sys.argv:
            s_idx = sys.argv.index("-day")
            selected_day = sys.argv[s_idx + 1]
            mplot.information["DAYS"] = str(selected_day)
        mplot.main()
        if mplot.output_file != "":
            print("Output summary file can be found in " + mplot.output_file)
        print("Finish .......")
        print("-----------------------------------------------------------")
        if "-pdf" in sys.argv:
            s_idx = sys.argv.index("-pdf")
            pdf_file = sys.argv[s_idx + 1] + ".pdf"
        else:
            pdf_file = mplot.output_pdf
        pp = PdfPages(pdf_file)
        for fig in range(1, plt.figure().number):
            plt.figure(fig).set_size_inches(20, 10)
            pp.savefig(fig, dpi=1000)
        pp.close()
        if "-onlypdf" not in sys.argv:
            plt.close(fig=6)
            plt.show()
