# TMS Integration: LINQO to WinSped

A professional data integration service that bridges **LINQO fleet management API** with **WinSped** by converting real-time vehicle position and driver status data from JSON format to WinSped-compatible text files.

---

##  Table of Contents

- [Local development setup (uv)](#local-development-setup-uv)
- [Business Problem](#business-problem)
- [Solution Overview](#solution-overview)
- [Features](#features)
- [Data Flow](#data-flow)
- [File Format](#file-format)
- [Project Structure](#project-structure)
- [Architecture](#architecture)

---

##  Local development setup (uv)

Requirements: Python 3.11+, Git, uv.

1. **Environment variables setup (.env-example)**

```env
# LINQ0 API Credentials
API_KEY_UA=your_linqo_api_key_ukraine
API_KEY_PL=your_linqo_api_key_poland

# FTP Server Configuration
FTP_HOST=your_ftp_host
FTP_PORT=your_ftp_port
FTP_USERNAME=your_username
FTP_PASSWORD=your_password
FTP_IMPORT_FOLDER=path to ftp folder to which files will be imported

# Driver ID Lists (JSON files with driver IDs)
DRIVER_ID_PATH_UA=data/drivers_ua.json
DRIVER_ID_PATH_PL=data/drivers_pl.json

# Vehicle ID Maps (validate vehicle IDs)
VEHICLE_ID_MAP_PATH_UA=data/vehicles_ua.json
VEHICLE_ID_MAP_PATH_PL=data/vehicles_pl.json
```

2. **Data Files Format**

**drivers.json**
```json
["LINQO_DRIVER_ID_1", "LINQO_DRIVER_ID_2", "LINQO_DRIVER_ID_2"]
```

**vehicles.json**
```json
{
  "LINQO_VEHICLE_ID_1": "PLATE_NUMBER_VEHICLE_1",
  "LINQO_VEHICLE_ID_2": "PLATE_NUMBER_VEHICLE_2",
  "LINQO_VEHICLE_ID_3": "PLATE_NUMBER_VEHICLE_3"
}
```

3. **Install uv (once)**
```bash
python -m pip install --user uv
```

4. **Create/update the virtual environment from uv.lock (recommended)**
```bash
uv sync --extra dev
```

5. **Run the service**
```bash
python src/tms_integration/main.py
```

Notes: uv sync synchronizes your environment to the lockfile and keeps the virtual environment consistent with it.

---

##  Business Problem

### Challenge
LINQO provides real-time fleet data (vehicle positions and driver information) through an API in JSON format. However, WinSped (LIS company's fleet analysis system) requires data in a specific text file format.

### Requirements
- **Real-time data integration** from LINQO API
- **Automatic format conversion** from JSON to WinSped text format
- **Support for multiple data types**: vehicle positions and driver status
- **Reliable delivery** to WinSped via FTP

---

##  Solution Overview

TMS Integration is an **automated, production-grade service** that:

1. **Listens to real-time position updates** from LINQO via Server-Sent Events (SSE)
2. **Polls driver information** periodically from LINQO API
3. **Transforms data** into WinSped-compliant format using Pydantic validators
4. **Uploads files** to FTP server on a scheduled basis

---

##  Features

### 1. Position Tracking
- **SSE stream listener** automatically receives position updates as vehicles move
- **In-Memory dictionary** maintains latest position for each vehicle
- **Automatic reconnection** with exponential backoff on connection loss
- **SQLite database** is used to store the data with WAL mode

### 2. Driver Status Tracking
- **Periodic API Polling** retrieves driver information at configurable intervals
- **Day-start information cached** to reduce API calls

---

##  Data Flow

### Position Data Flow

```
SSE Event (LINQ0)
    ↓
PositionTracker._process_event()
    ↓
Parse & Validate JSON
    ↓
Store in latest_positions dictionary
    ↓
Every [CONFIGURABLE_INTERVAL] minutes (default: 10):
    ├─ Read from dictionary
    ├─ Create Position models (with validators)
    ├─ Create LisInPosition payload
    ├─ Generate WinSped text format
    ├─ Upload to FTP
    └─ Save to SQLite database
```

### Driver Data Flow

```
DriverTracker.run() every [CONFIGURABLE_INTERVAL] minutes (default: 10)
    ↓
For each driver ID:
    ├─ Call LINQ0 API: current-time-analysis
    ├─ Parse response JSON
    ├─ Create Driver model (with validators)
    ├─ Store in latest_drivers dictionary
    └─ Fetch day-start info (cached)
        ↓
Create LisInDriver payload
    ↓
Generate WinSped text format
    ↓
Upload to FTP
```

---

##  Produced File Format

### Position File Format (message 15.txt)

```
15|20240115|103045|LINQO_VEHICLE_ID_1|0|PosBreite=0522735N|PosLaenge=0105123E|
15|20240115|103046|LINQO_VEHICLE_ID_2|0|PosBreite=0523145N|PosLaenge=0105456E|
```

### Driver File Format (message 499.txt)

```
499|20140128|0219|LKW||DriverCard1=LINQO_DRIVER_ID_1|DTCOCurrentActivity=Drive|DTCOCurrentActivityStart=20140128 005800|DTCOCurrentDriveMin=82|DTCONextBreakStart=20140128 041136|DTCONextBreakRemainMin=112|DTCODriverDayStart=20140127 151000|DTCODriverDayDriveRemainMin=112|DTCODayDriveMin=488|DTCODayWorkMin=670|DTCODayWorkRemainMin=230|DTCODayWorkEnd=20140128 060936|DTCOWeekDriveMin=488|DTCOWeekDriveRemainMin=2872|DTCOWeekWorkMin=495|DTCOWeekWorkRemainMin=3105|DTCODriverWeekStart=20140127 151000|DTCODriverWeekDriveMin=670|DTCODoubleWeekDriveMin=2553|DTCODoubleWeekDriveRemainMin=2847|DTCOLastWeekRestMin=2944|
499|20260608|1844|LKW||DriverCard1=LINQO_DRIVER_ID_2|DTCOCurrentActivity=Drive|DTCOCurrentActivityStart=20140128 005800|DTCOCurrentDriveMin=82|DTCONextBreakStart=20140128 041136|DTCONextBreakRemainMin=112|DTCODriverDayStart=20140127 151000|DTCODriverDayDriveRemainMin=112|DTCODayDriveMin=488|DTCODayWorkMin=670|DTCODayWorkRemainMin=230|DTCODayWorkEnd=20140128 060936|DTCOWeekDriveMin=488|DTCOWeekDriveRemainMin=2872|DTCOWeekWorkMin=495|DTCOWeekWorkRemainMin=3105|DTCODriverWeekStart=20140127 151000|DTCODriverWeekDriveMin=670|DTCODoubleWeekDriveMin=2553|DTCODoubleWeekDriveRemainMin=2847|DTCOLastWeekRestMin=2944|
```

---

##  Project Structure

```
tms_integration/
├── src/tms_integration/
│   ├── __init__.py
│   ├── tracker_manager.py               # Multi-tracker orchestration
│   │
│   ├── utils/
│   │   ├── config.py                    # Configuration management
        ├── logging_config.py            # Centralized logging setup
│   │   ├── ftp.py                       # FTP base class
│   │
│   └── winsped/
│       ├── lis_winsped.py               # WinSped FTP integration
│       ├── position_tracker.py          # Position data handler
│       ├── driver_tracker.py            # Driver status handler
│       │
│       └── models/
│           ├── lisin.py                 # LisIn payload models
│           └── types/
│               ├── position.py          # Position data model
│               └── driver.py            # Driver data model
│
├── .env                                 # Environment configuration
├── .gitignore
├── main.py                              # USAGE EXAMPLE / ENTRY POINT
├── requirements.txt
└── README.md
```

---

##  Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    LINQO API                                │
│  (JSON: positions, driver statuses, work information)       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
  ┌──────────────┐        ┌──────────────────┐
  │ SSE Stream   │        │ Driver API       │
  │ (Real-time   │        │ (Polled every    │
  │  positions)  │        │  10 minutes)     │
  └──────┬───────┘        └────────┬─────────┘
         │                         │
         ▼                         ▼
  ┌────────────────────────────────────────┐
  │   TMS Integration Service              │
  │  (Data Aggregation & Transformation)   │
  │                                        │
  │  • PositionTracker (SSE Listener)      │
  │  • DriverTracker (Periodic Polling)    │
  │  • Data Validators (Pydantic)          │
  │  • Report Generator (LisIn Models)     │
  └────────────────┬───────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   LisWinSped         │
        │   FTP Integration    │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   FTP Server         │
        │   (WinSped Import)   │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   WinSped System     │
        │   (Analysis Engine)  │
        └──────────────────────┘
```

### Threading Model

- **Main Thread**: controls MultiAPITracker orchestration
- **Position tracker threads**: 
  - SSE Listener for real-time position updates
  - Report Scheduler for generating reports
- **Driver tracker thread**: single polling thread for all drivers
