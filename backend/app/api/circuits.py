"""
Circuit Metadata
================
Static lookup table of F1 circuit information keyed by FastF1 Location field.

Updated for the 2025 season calendar.  Lap records reflect the fastest race
lap set at each venue (not qualifying).
"""

CIRCUIT_DATA: dict[str, dict] = {
    "Sakhir": {
        "circuit_name": "Bahrain International Circuit",
        "track_length_km": 5.412,
        "laps": 57,
        "lap_record": {"time": "1:31.447", "driver": "Pedro de la Rosa", "year": 2005},
        "first_gp": 2004,
        "circuit_type": "Purpose-built",
    },
    "Jeddah": {
        "circuit_name": "Jeddah Corniche Circuit",
        "track_length_km": 6.174,
        "laps": 50,
        "lap_record": {"time": "1:30.734", "driver": "Lewis Hamilton", "year": 2021},
        "first_gp": 2021,
        "circuit_type": "Street circuit",
    },
    "Melbourne": {
        "circuit_name": "Albert Park Circuit",
        "track_length_km": 5.278,
        "laps": 58,
        "lap_record": {"time": "1:19.813", "driver": "Charles Leclerc", "year": 2024},
        "first_gp": 1996,
        "circuit_type": "Street circuit",
    },
    "Suzuka": {
        "circuit_name": "Suzuka International Racing Course",
        "track_length_km": 5.807,
        "laps": 53,
        "lap_record": {"time": "1:30.983", "driver": "Lewis Hamilton", "year": 2019},
        "first_gp": 1987,
        "circuit_type": "Purpose-built",
    },
    "Shanghai": {
        "circuit_name": "Shanghai International Circuit",
        "track_length_km": 5.451,
        "laps": 56,
        "lap_record": {"time": "1:32.238", "driver": "Michael Schumacher", "year": 2004},
        "first_gp": 2004,
        "circuit_type": "Purpose-built",
    },
    "Miami": {
        "circuit_name": "Miami International Autodrome",
        "track_length_km": 5.412,
        "laps": 57,
        "lap_record": {"time": "1:29.708", "driver": "Max Verstappen", "year": 2023},
        "first_gp": 2022,
        "circuit_type": "Street circuit",
    },
    "Miami Gardens": {
        "circuit_name": "Miami International Autodrome",
        "track_length_km": 5.412,
        "laps": 57,
        "lap_record": {"time": "1:29.708", "driver": "Max Verstappen", "year": 2023},
        "first_gp": 2022,
        "circuit_type": "Street circuit",
    },
    "Imola": {
        "circuit_name": "Autodromo Enzo e Dino Ferrari",
        "track_length_km": 4.909,
        "laps": 63,
        "lap_record": {"time": "1:15.484", "driver": "Lewis Hamilton", "year": 2020},
        "first_gp": 1980,
        "circuit_type": "Purpose-built",
    },
    "Monte Carlo": {
        "circuit_name": "Circuit de Monaco",
        "track_length_km": 3.337,
        "laps": 78,
        "lap_record": {"time": "1:12.909", "driver": "Lewis Hamilton", "year": 2021},
        "first_gp": 1950,
        "circuit_type": "Street circuit",
    },
    "Monaco": {
        "circuit_name": "Circuit de Monaco",
        "track_length_km": 3.337,
        "laps": 78,
        "lap_record": {"time": "1:12.909", "driver": "Lewis Hamilton", "year": 2021},
        "first_gp": 1950,
        "circuit_type": "Street circuit",
    },
    "Barcelona": {
        "circuit_name": "Circuit de Barcelona-Catalunya",
        "track_length_km": 4.657,
        "laps": 66,
        "lap_record": {"time": "1:16.330", "driver": "Max Verstappen", "year": 2023},
        "first_gp": 1991,
        "circuit_type": "Purpose-built",
    },
    "Montréal": {
        "circuit_name": "Circuit Gilles Villeneuve",
        "track_length_km": 4.361,
        "laps": 70,
        "lap_record": {"time": "1:13.078", "driver": "Valtteri Bottas", "year": 2019},
        "first_gp": 1978,
        "circuit_type": "Semi-street circuit",
    },
    "Spielberg": {
        "circuit_name": "Red Bull Ring",
        "track_length_km": 4.318,
        "laps": 71,
        "lap_record": {"time": "1:05.619", "driver": "Carlos Sainz", "year": 2020},
        "first_gp": 1970,
        "circuit_type": "Purpose-built",
    },
    "Silverstone": {
        "circuit_name": "Silverstone Circuit",
        "track_length_km": 5.891,
        "laps": 52,
        "lap_record": {"time": "1:27.097", "driver": "Max Verstappen", "year": 2020},
        "first_gp": 1950,
        "circuit_type": "Purpose-built",
    },
    "Mogyoród": {
        "circuit_name": "Hungaroring",
        "track_length_km": 4.381,
        "laps": 70,
        "lap_record": {"time": "1:16.627", "driver": "Lewis Hamilton", "year": 2020},
        "first_gp": 1986,
        "circuit_type": "Purpose-built",
    },
    "Budapest": {
        "circuit_name": "Hungaroring",
        "track_length_km": 4.381,
        "laps": 70,
        "lap_record": {"time": "1:16.627", "driver": "Lewis Hamilton", "year": 2020},
        "first_gp": 1986,
        "circuit_type": "Purpose-built",
    },
    "Spa-Francorchamps": {
        "circuit_name": "Circuit de Spa-Francorchamps",
        "track_length_km": 7.004,
        "laps": 44,
        "lap_record": {"time": "1:46.286", "driver": "Valtteri Bottas", "year": 2018},
        "first_gp": 1950,
        "circuit_type": "Purpose-built",
    },
    "Stavelot": {
        "circuit_name": "Circuit de Spa-Francorchamps",
        "track_length_km": 7.004,
        "laps": 44,
        "lap_record": {"time": "1:46.286", "driver": "Valtteri Bottas", "year": 2018},
        "first_gp": 1950,
        "circuit_type": "Purpose-built",
    },
    "Zandvoort": {
        "circuit_name": "Circuit Zandvoort",
        "track_length_km": 4.259,
        "laps": 72,
        "lap_record": {"time": "1:11.097", "driver": "Lewis Hamilton", "year": 2021},
        "first_gp": 1952,
        "circuit_type": "Purpose-built",
    },
    "Monza": {
        "circuit_name": "Autodromo Nazionale Monza",
        "track_length_km": 5.793,
        "laps": 53,
        "lap_record": {"time": "1:21.046", "driver": "Rubens Barrichello", "year": 2004},
        "first_gp": 1950,
        "circuit_type": "Purpose-built",
    },
    "Baku": {
        "circuit_name": "Baku City Circuit",
        "track_length_km": 6.003,
        "laps": 51,
        "lap_record": {"time": "1:43.009", "driver": "Charles Leclerc", "year": 2019},
        "first_gp": 2016,
        "circuit_type": "Street circuit",
    },
    "Marina Bay": {
        "circuit_name": "Marina Bay Street Circuit",
        "track_length_km": 4.940,
        "laps": 62,
        "lap_record": {"time": "1:35.867", "driver": "Lewis Hamilton", "year": 2023},
        "first_gp": 2008,
        "circuit_type": "Street circuit",
    },
    "Singapore": {
        "circuit_name": "Marina Bay Street Circuit",
        "track_length_km": 4.940,
        "laps": 62,
        "lap_record": {"time": "1:35.867", "driver": "Lewis Hamilton", "year": 2023},
        "first_gp": 2008,
        "circuit_type": "Street circuit",
    },
    "Austin": {
        "circuit_name": "Circuit of the Americas",
        "track_length_km": 5.513,
        "laps": 56,
        "lap_record": {"time": "1:36.169", "driver": "Charles Leclerc", "year": 2019},
        "first_gp": 2012,
        "circuit_type": "Purpose-built",
    },
    "Mexico City": {
        "circuit_name": "Autódromo Hermanos Rodríguez",
        "track_length_km": 4.304,
        "laps": 71,
        "lap_record": {"time": "1:17.774", "driver": "Valtteri Bottas", "year": 2021},
        "first_gp": 1963,
        "circuit_type": "Purpose-built",
    },
    "São Paulo": {
        "circuit_name": "Autódromo José Carlos Pace (Interlagos)",
        "track_length_km": 4.309,
        "laps": 71,
        "lap_record": {"time": "1:10.540", "driver": "Valtteri Bottas", "year": 2018},
        "first_gp": 1973,
        "circuit_type": "Purpose-built",
    },
    "Las Vegas": {
        "circuit_name": "Las Vegas Strip Circuit",
        "track_length_km": 6.201,
        "laps": 50,
        "lap_record": {"time": "1:35.490", "driver": "Oscar Piastri", "year": 2024},
        "first_gp": 2023,
        "circuit_type": "Street circuit",
    },
    "Lusail": {
        "circuit_name": "Lusail International Circuit",
        "track_length_km": 5.419,
        "laps": 57,
        "lap_record": {"time": "1:24.319", "driver": "Max Verstappen", "year": 2023},
        "first_gp": 2021,
        "circuit_type": "Purpose-built",
    },
    "Yas Island": {
        "circuit_name": "Yas Marina Circuit",
        "track_length_km": 5.281,
        "laps": 58,
        "lap_record": {"time": "1:26.103", "driver": "Max Verstappen", "year": 2021},
        "first_gp": 2009,
        "circuit_type": "Purpose-built",
    },
    "Abu Dhabi": {
        "circuit_name": "Yas Marina Circuit",
        "track_length_km": 5.281,
        "laps": 58,
        "lap_record": {"time": "1:26.103", "driver": "Max Verstappen", "year": 2021},
        "first_gp": 2009,
        "circuit_type": "Purpose-built",
    },
    "Yas Marina": {
        "circuit_name": "Yas Marina Circuit",
        "track_length_km": 5.281,
        "laps": 58,
        "lap_record": {"time": "1:26.103", "driver": "Max Verstappen", "year": 2021},
        "first_gp": 2009,
        "circuit_type": "Purpose-built",
    },
    "Madrid": {
        "circuit_name": "Circuito de Madrid IFEMA",
        "track_length_km": 5.473,
        "laps": 66,
        "lap_record": {"time": "-", "driver": "-", "year": 0},
        "first_gp": 2026,
        "circuit_type": "Purpose-built",
    },
}


def get_circuit_info(location: str) -> dict | None:
    """Look up circuit metadata by Location string from the schedule.

    The schedule provides locations like ``"Sakhir, Bahrain"`` — we try the
    full string first, then just the city part (before the comma).
    """
    if location in CIRCUIT_DATA:
        return CIRCUIT_DATA[location]
    city = location.split(",")[0].strip()
    return CIRCUIT_DATA.get(city)
