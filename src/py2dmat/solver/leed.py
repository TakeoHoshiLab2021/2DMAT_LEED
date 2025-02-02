# 2DMAT -- Data-analysis software of quantum beam diffraction experiments for 2D material structure
# Copyright (C) 2020- The University of Tokyo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see http://www.gnu.org/licenses/.

from typing import List
import itertools
import os
import os.path
import shutil
from distutils.dir_util import copy_tree
from pathlib import Path

import numpy as np

import py2dmat
from py2dmat import exception
import subprocess


class Solver(py2dmat.solver.SolverBase):
    path_to_first_solver: Path
    path_to_second_solver: Path
    dimension: int

    def __init__(self, info: py2dmat.Info):
        super().__init__(info)

        self._name = "leed"
        info_s = info.solver

        # With or without work directory generation
        self.remove_work_dir = info_s["post"].get("remove_work_dir", False)

        # Check keywords
        def check_keywords(key, segment, registered_list):
            if (key in registered_list) is False:
                msg = "Error: {} in {} is not correct keyword.".format(key, segment)
                raise RuntimeError(msg)

        keywords_solver = ["name", "config", "reference", "post"]
        keywords = {}
        keywords["config"] = ["path_to_first_solver","path_to_second_solver"]
        keywords["reference"] = ["path_to_base_dir"]
        keywords["post"] = ["remove_work_dir"]

        for key in info_s.keys():
            check_keywords(key, "solver", keywords_solver)
            if key == "name":
                continue
            for key_child in info_s[key].keys():
                check_keywords(key_child, key, keywords[key])

        # Set new environment
        p1solver = info_s["config"].get("path_to_first_solver", "satl1.exe")
        if os.path.dirname(p1solver) != "":
            # ignore ENV[PATH]
            self.path_to_first_solver = self.root_dir / Path(p1solver).expanduser()
        else:
            for P in itertools.chain([self.root_dir], os.environ["PATH"].split(":")):
                self.path_to_first_solver = Path(P) / p1solver
                if os.access(self.path_to_first_solver, mode=os.X_OK):
                    break
        if not os.access(self.path_to_first_solver, mode=os.X_OK):
            raise exception.InputError(f"ERROR: solver ({p1solver}) is not found")

        # Set environment
        p2solver = info_s["config"].get("path_to_second_solver", "satl2.exe")
        if os.path.dirname(p2solver) != "":
            # ignore ENV[PATH]
            self.path_to_second_solver = self.root_dir / Path(p2solver).expanduser()
        else:
            for P in itertools.chain([self.root_dir], os.environ["PATH"].split(":")):
                self.path_to_second_solver = Path(P) / p2solver
                if os.access(self.path_to_second_solver, mode=os.X_OK):
                    break
        if not os.access(self.path_to_second_solver, mode=os.X_OK):
            raise exception.InputError(f"ERROR: solver ({p2solver}) is not found")

        self.path_to_base_dir = info_s["reference"]["path_to_base_dir"]
        # check files
        files = ["exp.d", "rfac.d", "tleed4.i", "tleed5.i"]
        for file in files:
            if not os.path.exists(os.path.join(self.path_to_base_dir, file)):
                raise exception.InputError(
                    f"ERROR: input file ({file}) is not found in ({self.path_to_base_dir})"
                )
        self.input = Solver.Input(info)

    def prepare(self, message: py2dmat.Message) -> None:
        subdir = self.input.subdir(message)
        self.work_dir = self.proc_dir / Path(subdir)
        for dir in [self.path_to_base_dir]:
            copy_tree(os.path.join(self.root_dir, dir), os.path.join(self.work_dir))
        cwd = os.getcwd()
        os.chdir(self.work_dir)
        self.input.prepare(message)
        os.chdir(cwd)
    

    def run(self, nprocs: int = 1, nthreads: int = 1) -> None:
        try:
            super()._run_by_subprocess([str(self.path_to_first_solver)])
            super()._run_by_subprocess([str(self.path_to_second_solver)])
        except subprocess.CalledProcessError:
            print("エラーが発生しました")

    def get_results(self) -> float:
        # Get R-factor
        if not os.path.exists(os.path.join(self.work_dir, "iv 1")):
           rfactor = float('inf')
        filename = os.path.join(self.work_dir, "search.s")
        with open(filename, "r") as fr:
            lines = fr.readlines()
            for line in lines:
                if "R-FACTOR" in line:
                    rfactor = float(line.split("=")[1])
                    break

        #remove work directory 
        if self.remove_work_dir == "true":
            shutil.rmtree(self.work_dir)
        return rfactor
        
        

    class Input(object):
        root_dir: Path
        output_dir: Path
        dimension: int
        string_list: List[str]

        def __init__(self, info):
            self.dimension = info.base["dimension"]
            self.root_dir = info.base["root_dir"]
            self.output_dir = info.base["output_dir"]

        #Prepare directory names for each point calculation to be stored in a separate directory
        def _pre_dir(self, Log_number, iset):
            folder_name = "Log{:08d}_{:08d}".format(Log_number, iset)
            os.makedirs(folder_name, exist_ok=True)
            return folder_name

        #Create subdirectories
        def subdir(self, message: py2dmat.Message):
            x_list = message.x
            step = message.step
            iset = message.set
            folder_name = self._pre_dir(step, iset)
            return folder_name

        def prepare(self, message: py2dmat.Message):
            x_list = message.x
            self._write_fit_file(x_list)    


        def _write_fit_file(self, variables):
            with open("tleed5.i", "r") as fr:
                contents = fr.read()
            for idx, variable in enumerate(variables):
            # FORTRAN format: F7.4
                svariable = "{:7.4f}".format(float(variable))
                contents = contents.replace(
                    "opt{}".format(str(idx).zfill(4)), svariable
                )

            with open("tleed5.i", "w") as writer:
                writer.write(contents)