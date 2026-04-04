{
  "scenario_id": "wildfire_001",
  "time_step_sec": 60,
  "duration_sec": 3600,
  "location_bounds": {
    "lat_min": 34.0,
    "lat_max": 34.1,
    "lon_min": -118.3,
    "lon_max": -118.2
  },
  "sensors": [
    {
      "sensor_id": "thermal_cam_1",
      "type": "thermal_camera",
      "unit": "Celsius",
      "data": [
        {"timestamp": 0, "grid": [[22,23,21],[23,24,22],[22,23,21]]},
        {"timestamp": 60, "grid": [[23,25,22],[25,27,23],[23,25,22]]},
        {"timestamp": 120, "grid": [[24,27,23],[27,30,24],[24,27,23]]}
      ]
    },
    {
      "sensor_id": "wind_1",
      "type": "wind_sensor",
      "unit": "m/s",
      "data": [
        {"timestamp": 0, "speed": 3.2, "direction_deg": 45},
        {"timestamp": 60, "speed": 3.5, "direction_deg": 50},
        {"timestamp": 120, "speed": 4.0, "direction_deg": 55}
      ]
    },
    {
      "sensor_id": "soil_1",
      "type": "ground_sensor",
      "unit": "percent / C",
      "data": [
        {"timestamp": 0, "moisture": 12, "temperature": 20},
        {"timestamp": 60, "moisture": 11.8, "temperature": 21},
        {"timestamp": 120, "moisture": 11.5, "temperature": 22}
      ]
    },
    {
      "sensor_id": "smoke_1",
      "type": "smoke_sensor",
      "unit": "PM2.5",
      "data": [
        {"timestamp": 0, "pm25": 5},
        {"timestamp": 60, "pm25": 12},
        {"timestamp": 120, "pm25": 35}
      ]
    },
    {
      "sensor_id": "human_report_1",
      "type": "text_report",
      "data": [
        {"timestamp": 0, "text": "No visible smoke"},
        {"timestamp": 120, "text": "Smoke spotted near north-east boundary"}
      ]
    }
  ],
  "ground_truth_fire": [
    {"timestamp": 0, "fire_cells": []},
    {"timestamp": 60, "fire_cells": [[1,1]]},
    {"timestamp": 120, "fire_cells": [[1,1],[1,2],[2,1]]}
  ]
}