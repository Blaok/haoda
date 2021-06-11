import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from typing import BinaryIO, Dict, Optional, TextIO

from haoda import util
from haoda.backend import xilinx as backend

__all__ = (
    'ReportDirUtil',
    'ReportXoUtil',
    'RtlHlsInfo',
)

REPORT_UTIL_COMMANDS = r'''
read_verilog [ glob {hdl_dir}/*.v ]
set ips [ glob -nocomplain {hdl_dir}/*/*.xci ]
if {{ $ips ne "" }} {{
  read_ip $ips
  generate_target synthesis [ get_files *.xci ]
}}
foreach tcl_file [glob -nocomplain {hdl_dir}/*.tcl] {{
  source $tcl_file
}}
{set_parallel}
synth_design {synth_args}
opt_design
report_utilization {report_util_args}
'''


class ReportDirUtil(backend.Vivado):
  """Run synthesis and generate resource utilization report.

  This class is a child of subprocess.Popen and will launch Vivado to run
  synthesis and generate resource utilization report. Arguments passed to
  synth_design and report_utilization can be configured via the kwargs params.

  Attributes:
    job_server_fd: Optional file descriptor of a job server.
    num_jobs: Optional number of jobs.
  """

  def __init__(
      self,
      hdl_dir: str,
      rpt_path: str,
      top_name: str,
      part_num: Optional[str] = None,
      synth_kwargs: Optional[Dict[str, str]] = None,
      report_util_kwargs: Optional[Dict[str, str]] = None,
  ):
    """Run synthesis and generate resource utilization report.

    Args:
      hdl_dir: HDL directory containing *.v and *.tcl files.
      rpt_file: Path of generated resource utilization report.
      top_name: Top module name.
      part_num: Part number; infered from HDL if empty.
      synth_kwargs: Additional arguments for synth_design.
      report_util_kwargs: Additional arguments for report_utilization.

    Raises:
      InputError if part number cannot be inferred.
    """
    if part_num is None:
      for hdl_file_format in ('{}.v', '{0}_{0}.v'):
        try:
          with open(os.path.join(
              hdl_dir,
              hdl_file_format.format(top_name),
          )) as hdl_file:
            part_num = RtlHlsInfo(hdl_file)['HLS_INPUT_PART']
          break
        except FileNotFoundError:
          pass
    if part_num is None:
      raise util.InputError('failed to infer part number')

    if synth_kwargs is None:
      synth_kwargs = {}
    synth_kwargs['top'] = top_name
    synth_kwargs['part'] = part_num

    if report_util_kwargs is None:
      report_util_kwargs = {}
    report_util_kwargs['file'] = os.path.abspath(rpt_path)
    report_util_kwargs.setdefault('hierarchical', '')

    synth_args = ' '.join(f'-{k} {v}' for k, v in synth_kwargs.items())
    report_util_args = ' '.join(
        f'-{k} {v}' for k, v in report_util_kwargs.items())
    kwargs = {
        'hdl_dir': os.path.abspath(hdl_dir),
        'synth_args': synth_args,
        'report_util_args': report_util_args,
        'set_parallel': '',
    }
    self.job_server_fd = util.get_job_server_fd(())
    if self.job_server_fd is not None:
      new_fd = os.open('/proc/self/fd/%d' % self.job_server_fd,
                       os.O_RDWR | os.O_NONBLOCK)
      self.num_jobs = 1  # maximum supported by Vivado is 8
      try:
        for i in range(7):
          self.num_jobs += len(os.read(new_fd, 1))
      except BlockingIOError as e:
        pass
      os.close(new_fd)
      kwargs['set_parallel'] = 'set_param general.maxThreads %d' % self.num_jobs
    super().__init__(REPORT_UTIL_COMMANDS.format(**kwargs))

  def __exit__(self, *args):
    super().__exit__(*args)
    if self.job_server_fd is not None:
      os.write(self.job_server_fd, b'x' * (self.num_jobs - 1))


class ReportXoUtil(ReportDirUtil):
  """Run synthesis and generate resource utilization report.

  This class is a child of subprocess.Popen and will launch Vivado to run
  synthesis and generate resource utilization report. Arguments passed to
  synth_design and report_utilization can be configured via the kwargs params.

  Attributes:
    tmpdir: Temporary working directory for the RTL files and generated report.
    rpt_file: File object of generated resource utilization report.
    rpt_file_name: Name of the generated temporary resource utilization report.
  """

  def __init__(self,
               xo_file: BinaryIO,
               rpt_file: TextIO,
               top_name: str = 'Dataflow',
               part_num: Optional[str] = None,
               synth_kwargs: Optional[Dict[str, str]] = None,
               report_util_kwargs: Optional[Dict[str, str]] = None):
    """Run synthesis and generate resource utilization report.

    Args:
      xo_file: XO file object containing the HDL files.
      rpt_file: File object of generated resource utilization report.
      top_name: Optionally specify a different top name other than "Dataflow";
          inferred from XO file if empty.
      part_num: Optionally specify a different part number other than
          automatically determined.
      synth_kwargs: Dict of arguments for the synth_design command.
      report_util_kwargs: Dict of arguments for the synth_design command.

    Raises:
      InputError: if input is not a valid XO.
      InternalError: if the report is not generated as expected.
    """
    self.tmpdir = tempfile.TemporaryDirectory(prefix='report-xo-util-')
    self.rpt_file = rpt_file
    self.rpt_file_name = os.path.join(self.tmpdir.name, 'post_synth_util.rpt')
    with zipfile.ZipFile(xo_file) as xo_zip:
      with xo_zip.open('xo.xml') as xo_xml:
        kernel = ET.parse(xo_xml).find('./Kernels/Kernel')
        if kernel is None:
          raise util.InputError('cannot parse XO file')
        ip_dir = kernel.attrib['IP']
        kernel_name = kernel.attrib['Name']
      hdl_dir_prefix = ip_dir + '/src'
      if all(not x.startswith(hdl_dir_prefix) for x in xo_zip.namelist()):
        hdl_dir_prefix = ip_dir + '/hdl/verilog'
      hdl_dir = os.path.join(self.tmpdir.name, hdl_dir_prefix)
      xo_zip.extractall(path=self.tmpdir.name,
                        members=[
                            name for name in xo_zip.namelist()
                            if name.startswith(hdl_dir_prefix)
                        ])

    if not top_name:
      top_name = kernel_name

    super().__init__(
        hdl_dir,
        self.rpt_file_name,
        top_name,
        part_num,
        synth_kwargs,
        report_util_kwargs,
    )

  def __exit__(self, *args):
    super().__exit__(*args)
    try:
      with open(self.rpt_file_name) as src_rpt_file:
        shutil.copyfileobj(src_rpt_file, self.rpt_file)
    except FileNotFoundError:
      raise util.InternalError('failed to generate report file')
    self.tmpdir.cleanup()


RTL_HLS_INFO_REGEX = r'\(\* CORE_GENERATION_INFO\s*=\s*".*,\{(.*)\}" \*\)'


class RtlHlsInfo:

  def __init__(self, rtl_file: TextIO):
    match = re.search(RTL_HLS_INFO_REGEX, rtl_file.read())
    if match is None:
      raise util.InputError('cannot parse RTL file')
    for item in match.group(1).split(','):
      key, value = item.split('=')
      setattr(self, key, value)

  def __getitem__(self, key: str) -> str:
    return getattr(self, key)
