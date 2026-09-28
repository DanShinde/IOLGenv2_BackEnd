"""Generates the Siemens TIA SCL that maps the input, output and HMI-test data blocks.

Pure text templating -- stdlib only, no HTTP, no DB.

Ported from TextLists/script.py::createSCL, which took (IBytes, QBytes, IODB) but used
only QBytes and IODB: the input image size was accepted and dropped on the floor, and
the input/output DB numbers were hardcoded as 1 and 2 in the body even though the
comment header claimed to describe them. All five values are real parameters here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SclParams:
    """Defaults are the values the legacy app hardcoded, so pressing Generate without
    touching anything reproduces what it always produced."""
    output_bytes: int = 10
    input_bytes: int = 5
    input_db: int = 1
    output_db: int = 2
    hmi_io_db: int = 10


def render_scl(params):
    """Returns the SCL source as text."""
    # The input-image line is the one deliberate addition to the legacy output: the form
    # exposes input_bytes, so it has to show up somewhere or the field would look broken
    # to anyone who changes it and diffs the result.
    return f"""// DB Number {params.input_db} is used for Inputs
// DB Number {params.output_db} is used for Outputs
// DB Number {params.hmi_io_db} is used for HMI IO
// Input image size: {params.input_bytes} bytes / Output image size: {params.output_bytes} bytes

//Output Mapping
IF NOT "HMI_IO".Q_Test_Mode THEN
    POKE_BLK(area_src := 16#84,
             dbNumber_src := {params.output_db}, //Output DB Number
             byteOffset_src := 0,
             area_dest := 16#82,
             dbNumber_dest := 0,
             byteOffset_dest := 0,
             count := {params.output_bytes});

    //HMI Output Testing mode
ELSE
    POKE_BLK(area_src := 16#84,
             dbNumber_src := {params.hmi_io_db},
             byteOffset_src := 6,
             area_dest := 16#82,
             dbNumber_dest := 0,
             byteOffset_dest := "HMI_IO".IO_Pointer,
             count := 1,
             ENO => ENO);
END_IF;

//HMI Input Status
        POKE_BLK(area_src := 16#84,
                 dbNumber_src := {params.input_db},   //Input DB Number
                 byteOffset_src := ("HMI_IO".HMI_IO_Pointer * 2),  // 2 for 16 IOs per screen, 4 for 32 IOs per screen
                 area_dest := 16#84,
                 dbNumber_dest := {params.hmi_io_db},
                 byteOffset_dest := 2,
                 count := 2,
                 ENO => ENO);

//HMI Output Status
        POKE_BLK(area_src := 16#82,
                 dbNumber_src := 0,
                 byteOffset_src := ("HMI_IO".HMI_IO_Pointer *2),  // 2 for 16 IOs per screen, 4 for 32 IOs per screen
                 area_dest := 16#84,
                 dbNumber_dest := {params.hmi_io_db},
                 byteOffset_dest := 4,
                 count := 2,
                 ENO => ENO);

//HMI Output for testing Status
        POKE_BLK(area_src := 16#82,
                 dbNumber_src := 0,
                 byteOffset_src := ("HMI_IO".HMI_IO_Pointer),
                 area_dest := 16#84,
                 dbNumber_dest := {params.hmi_io_db},
                 byteOffset_dest := 7,
                 count := 1,
                 ENO => ENO);
"""
