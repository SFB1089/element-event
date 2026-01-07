"""Events are linked to Trials"""

import datajoint as dj
import inspect
import importlib 
from element_calcium_imaging import scan #TR23: there is probably a better method to import scan - but this works

schema = dj.schema() 

_linking_module = None


def activate(schema_name, *, create_schema=True, create_tables=True,
             linking_module=None):
    """
    activate(schema_name, *, create_schema=True, create_tables=True,
             linking_module=None)
        :param schema_name: schema name on the database server to activate
                            the `behavior` element
        :param create_schema: when True (default), create schema in the
                              database if it does not yet exist.
        :param create_tables: when True (default), create tables in the
                              database if they do not yet exist.
        :param linking_module: a module (or name) containing the required
                               dependencies to activate the `event` element:
            Upstream tables:
                + Session: parent table to BehaviorRecording, typically
                           identifying a recording session.
            Functions:
                + get_experiment_root_data_dir() -> list
                    Retrieve the root data director(y/ies) with behavioral
                    recordings (e.g., bpod files) for all subject/sessions.
                    :return: a string for full path to the root data directory
                + get_session_directory(session_key: dict) -> str
                    Retrieve the session directory containing the recording(s)
                    for a given Session
                    :param session_key: a dictionary of one Session `key`
                    :return: a string for full path to the session directory
    """
    if isinstance(linking_module, str):
        linking_module = importlib.import_module(linking_module)
    assert inspect.ismodule(linking_module), "The argument 'dependency' must"\
                                             + " be a module or module name"

    schema.activate(schema_name, create_schema=create_schema,
                    create_tables=create_tables,
                    add_objects=linking_module.__dict__)

# -------------- Functions required by the element-trial   ---------------


def get_experiment_root_data_dir() -> list:
    """
    All data paths, directories in DataJoint Elements are recommended to be
    stored as relative paths, with respect to some user-configured "root"
    directory, which varies from machine to machine

    get_experiment_root_data_dir() -> list
        This user-provided function retrieves the list of possible root data
        directories containing the behavioral data for all subjects/sessions
        :return: a string for full path to the behavioral root data directory,
         or list of strings for possible root data directories
    """
    return _linking_module.get_experiment_root_data_dir()


def get_session_directory(session_key: dict) -> str:
    """
    get_session_directory(session_key: dict) -> str
        Retrieve the session directory containing the
         recorded data for a given Session
        :param session_key: a dictionary of one Session `key`
        :return: a string for full path to the session directory
    """
    return _linking_module.get_session_directory(session_key)


# ----------------------------- Table declarations ----------------------


@schema
class EventType(dj.Lookup):
    definition = """
    event_type                : varchar(300)
    ---
    event_type_description='' : varchar(300)
    """


@schema
class BehaviorRecording(dj.Manual):
    definition = """
    -> Session
    -> scan.Scan 
    ---
    recording_start_time=null : datetime
    recording_duration=null   : float
    recording_notes=''     : varchar(256)
    """

    class File(dj.Part):
        definition = """
        -> master
        filepath              : varchar(300)
        """


@schema
class Event(dj.Imported):
    definition = """
    -> BehaviorRecording
    -> EventType
    event_start_time          : decimal(11,5)  # (second) relative to recording start
    ---
    event_end_time=null       : decimal(11,5)  # (second) relative to recording start
    """


"""
----- AlignmentEvent -----
The following `AlignmentEvent` table is designed to provide a mechanism for
performing event-aligned analyses, such as Peristimulus Time Histogram (PSTH) analysis 
commonly used in electrophysiology studies.
One entry in the `AlignmentEvent` table defines an event type to align signal/activity
    timeseries to.
Start and end event types define the beginning and end of a data window
time_shift is seconds of adjustment with respect to the alignment variable, or the
    beginning/end of the window via start/end event types
"""


@schema
class AlignmentEvent(dj.Manual):
    definition = """ # time_shift is seconds to shift with respect to (WRT) a variable
    alignment_name: varchar(32)
    ---
    alignment_description='': varchar(1000)  
    -> EventType.proj(alignment_event_type='event_type') # event type to align to
    alignment_time_shift: float                      # (s) WRT alignment_event_type
    -> EventType.proj(start_event_type='event_type') # event before alignment_event_type
    start_time_shift: float                          # (s) WRT start_event_type
    -> EventType.proj(end_event_type='event_type')   # event after alignment_event_type
    end_time_shift: float                            # (s) WRT end_event_type
    """
    # WRT - with respect to
    
    
@schema
class InterpolationType(dj.Lookup):
    """Types of interpolation/correction applied to event timestamps"""
    definition = """
    interpolation_type          : varchar(32)
    ---
    interpolation_description='' : varchar(256)
    """
    contents = [
        ('LEADING_ZERO', 'Leading NaN/zero frames replaced with 0'),
        ('DUPLICATE_SEQ', 'Repeated sequence detected and zeroed'),
        ('PATTERN_446', '4,4,6 pattern corrected to 4,5,5'),
        ('BAD_DIFF', 'Invalid diff corrected using predicted increment'),
        ('INTERPOLATED', 'Zero frame filled via linear interpolation'),
        ('EXTRAPOLATED_LEADING', 'Leading zero extrapolated backwards'),
        ('EXTRAPOLATED_TRAILING', 'Trailing zero extrapolated forwards'),
        ('INTERPOLATED_SYNTHETIC', 'No valid frames - synthetic sequence generated'),
    ]


@schema
class EventInterpolation(dj.Manual):
    """Log of interpolated/corrected events linked to their source Event"""
    definition = """
    -> Event
    frame_idx                   : int           # eye camera frame index
    ---
    -> InterpolationType
    original_value              : int           # original frame index before correction
    corrected_value             : int           # corrected frame index after interpolation
    diff_before=null            : int           # diff to previous frame before correction
    diff_after=null             : int           # diff to previous frame after correction  
    details=''                  : varchar(256)  # additional correction details
    """


@schema
class CameraTimestamps(dj.Manual):
    """
    Raw camera timestamp data for sanity checking and fallback.
    
    Stores uncorrected data from two independent sources:
    1. raw_ocr_frame_indices: Raw OptiTrack frame numbers extracted via OCR 
       from eye camera video overlay (before any correction/interpolation)
    2. csv_timestamps: High-precision timestamps from Bonsai-RX CSV files
       (ISO 8601 format with sub-millisecond precision)
    
    This table provides a final sanity check and fallback mechanism by 
    preserving the original, uncorrected data from both independent 
    timestamp sources. Each array entry corresponds to one eye camera frame.
    """
    definition = """
    -> BehaviorRecording
    -> EventType                                    # e.g., 'mini2p1_eye_left_frames' or 'mini2p1_eye_right_frames'
    ---
    raw_ocr_frame_indices       : longblob          # Raw OCR-extracted OptiTrack frame numbers (no correction)
    csv_timestamps              : longblob          # Bonsai-RX timestamps from CSV (seconds, float64)
    csv_timestamps_iso          : longblob          # Original ISO 8601 timestamp strings from CSV
    csv_start_datetime          : datetime(6)       # First CSV timestamp as datetime (for reference)
    n_frames                    : int unsigned      # Total number of eye camera frames
    n_valid_ocr                 : int unsigned      # Number of frames with valid OCR readings
    n_csv_timestamps            : int unsigned      # Number of CSV timestamp entries
    frame_rate_csv_hz           : float             # Estimated frame rate from CSV intervals (Hz)
    csv_duration_sec            : float             # Total duration from CSV timestamps (seconds)
    notes=''                    : varchar(1024)     # Processing notes or warnings
    """

