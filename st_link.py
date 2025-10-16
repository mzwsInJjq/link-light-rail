#!/usr/bin/env python3

import argparse
import requests
import json
from dataclasses import dataclass
import time
from typing import List

api_key = "YOUR_API_KEY"

parser = argparse.ArgumentParser(description="Seattle Link Light Rail Train Tracker")
parser.add_argument('-l', '--line', type=str, choices=['1', '2', 'T'], default='1', help='Line to track (default: 1)')
args = parser.parse_args()
line_to_route_id = {
    '1': '40_100479',
    '2': '40_2LINE',
    'T': '40_TLINE'}
directions = {
    '1': ('S', 'N'),
    '2': (-1, 0),
    'T': (0, -1)}

route_id = line_to_route_id[args.line]
url = f"https://api.pugetsound.onebusaway.org/api/where/trips-for-route/{route_id}.json?key={api_key}"

@dataclass
class Train():
    id: str
    vehicle_id: str
    direction: str
    next_station_index: int
    next_station: str
    time_until: str
    leg_total: str
    pct_distance_along_trip: float

    def __str__(self):
        return f"""
{"\033[1;41m" + self.direction + "\033[0m"} {"\033[1;44m" + self.vehicle_id + "\033[0m"}
{"\033[1;33m" + self.next_station} in {round(self.time_until)}s\033[0m"""

class TrainGetter():
    def __init__(self) -> None:
        self.stop_id_to_name = {}
        match args.line:
            case '1':
                self.name_to_index = {
                    "Federal Way Downtown": 0,
                    "Star Lake": 1,
                    "Kent Des Moines": 2,
                    "Angle Lake" : 3,
                    "SeaTac/Airport": 4,
                    "Tukwila Int'l Blvd": 5,
                    "Rainier Beach": 6,
                    "Othello": 7,
                    "Columbia City": 8,
                    "Mount Baker": 9,
                    "Beacon Hill": 10,
                    "SODO": 11,
                    "Stadium": 12,
                    "Int'l Dist/Chinatown": 13,
                    "Pioneer Square": 14,
                    "Symphony": 15,
                    "Westlake": 16,
                    "Capitol Hill": 17,
                    "Univ of Washington": 18,
                    "U District": 19,
                    "Roosevelt": 20,
                    "Northgate": 21,
                    "Shoreline South/148th": 22,
                    "Shoreline North/185th": 23,
                    "Mountlake Terrace": 24,
                    "Lynnwood City Center": 25
                }
            case '2':
                self.name_to_index = {
                    "South Bellevue": 0,
                    "East Main": 1,
                    "Bellevue Downtown": 2,
                    "Wilburton": 3,
                    "Spring District": 4,
                    "BelRed": 5,
                    "Overlake Village": 6,
                    "Redmond Technology": 7,
                    "Marymoor Village": 8,
                    "Downtown Redmond": 9
                }
            case 'T':
                self.name_to_index = {
                    "Tacoma Dome" : 0,
                    "S 25th": 1,
                    "Union Station": 2,
                    "Convention Center": 3,
                    "Theater District": 4,
                    "Old City Hall": 5,
                    "S 4th": 6,
                    "Stadium District": 7,
                    "Tacoma General": 8,
                    "6th Ave": 9,
                    "Hilltop District": 10,
                    "St Joseph": 11
                }

        # precompute helpers used frequently to avoid repeated work
        self.station_names = list(self.name_to_index.keys())
        self.line_directions = directions[args.route]
        self.endpoint_name = (max(self.name_to_index, key=self.name_to_index.get)
                              if isinstance(self.line_directions[1], int)
                              else self.line_directions[1])
        # trip-direction map is built once per API response in get_direction()
        self._trip_direction_map = None

    def station_id_to_name(self, id):
        return self.stop_id_to_name.get(id)

    def station_name_to_index(self, name):
        return self.name_to_index[name]
    
    def get_direction(self, trip_id, api_dict):
        # Build a trip-id -> direction-name map once per response (cached)
        if self._trip_direction_map is None:
            ld0, ld1 = self.line_directions
            tmap = {}
            for trip in api_dict["data"]["references"]["trips"]:
                if trip["directionId"] == "0":
                    tmap[trip["id"]] = (self.station_names[ld0] if isinstance(ld0, int) else ld0)
                else:
                    tmap[trip["id"]] = (self.station_names[ld1] if isinstance(ld1, int) else ld1)
            self._trip_direction_map = tmap

        try:
            return self._trip_direction_map[trip_id]
        except KeyError:
            raise ValueError(f"Trip id {trip_id} not found")

    def get_next_station(self, trip_dict):
        # be tolerant if status or nextStop missing
        status = trip_dict.get("status") or {}
        next_stop_id = status.get("nextStop")
        if not next_stop_id:
            return "(no next stop)", -1
        name = self.station_id_to_name(next_stop_id)
        if not name:
            return "(unknown stop)", -1
        index = self.station_name_to_index(name)
        return name, index
    
    def get_trains(self, json_str) -> List[Train]:
        api_dict = json.loads(json_str)
        # build stop id -> name mapping once per response
        self.stop_id_to_name = {stop["id"]: stop["name"] for stop in api_dict["data"]["references"]["stops"]}
        # clear per-response cache
        self._trip_direction_map = None
        out = []
        for trip in api_dict["data"]["list"]:
            # skip trips with no status
            if "status" not in trip:
                print(f"Skipping trip without status (tripId={trip.get('tripId','?')})")
                continue
            try:
                t = self.process_train(trip, api_dict)
                out.append(t)
            except Exception as e:
                print(f"Error processing trip {trip.get('tripId','?')}, skipping: {e}")
                continue
        endpoint = self.endpoint_name
        for t_sorted in sorted(out, key=lambda x: (-x.next_station_index + (x.direction == endpoint), x.pct_distance_along_trip)):
            print(t_sorted)
            # print((-t_sorted.next_station_index + (t_sorted.direction == (max(self.name_to_index, key=self.name_to_index.get) if isinstance(directions[args.route][1], int) else directions[args.route][1])), t_sorted.pct_distance_along_trip))
        return out

    def get_leg_time(self, trip_dict):
        # tolerant lookup: if schedule or nextStop missing, return 0
        next_stop_id = trip_dict.get("status", {}).get("nextStop")
        schedule = trip_dict.get("schedule", {})
        stop_times = schedule.get("stopTimes", []) if schedule else []
        if not next_stop_id or not stop_times:
            return 0
        for i, stop in enumerate(stop_times):
            if stop.get("stopId") == next_stop_id:
                if i == 0:
                    return 0
                prev = stop_times[i - 1].get("departureTime", 0)
                return stop.get("arrivalTime", 0) - prev
        return 0

    def process_train(self, trip_dict, api_dict):
        next_station_name, next_station_index = self.get_next_station(trip_dict)
        now = time.time()
        updated = trip_dict["status"]["lastUpdateTime"] / 1000
        staleness = now - updated
        time_to_next_stop = max(trip_dict["status"]["nextStopTimeOffset"] - staleness, 0)

        trip_id = trip_dict["tripId"]
        vehicle_id = trip_dict["status"]["vehicleId"]
        if not vehicle_id:
            vehicle_id = " " * 13 if args.route != 'T' else " " * 4
        direction = self.get_direction(trip_id, api_dict)

        # compare direction to the selected endpoint (use parentheses to force correct grouping)
        if direction == (max(self.name_to_index, key=self.name_to_index.get) if isinstance(directions[args.route][1], int) else directions[args.route][1]):
            pct_distance_along_trip = 1 - (trip_dict["status"]["scheduledDistanceAlongTrip"] / trip_dict["status"]["totalDistanceAlongTrip"])
        else:
            pct_distance_along_trip = trip_dict["status"]["scheduledDistanceAlongTrip"] / trip_dict["status"]["totalDistanceAlongTrip"]

        return Train(
            id=trip_id,
            vehicle_id=vehicle_id,
            direction=direction,
            next_station_index=next_station_index,
            next_station=next_station_name,
            time_until=time_to_next_stop,
            leg_total=self.get_leg_time(trip_dict),
            pct_distance_along_trip=pct_distance_along_trip
        )

if __name__ == "__main__":
    response = requests.get(url)

    if response.status_code == 200:
        traingetter = TrainGetter()
        traingetter.get_trains(json_str=response.text)

    else:
        print("Request failed")
        exit()
