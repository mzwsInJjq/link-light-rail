import requests
import json
import sys

api_key = "YOUR_API_KEY"
url_t = f"https://api.pugetsound.onebusaway.org/api/where/stops-for-route/40_TLINE.json?key={api_key}"
url_1 = f"https://api.pugetsound.onebusaway.org/api/where/stops-for-route/40_100479.json?key={api_key}"
url_2 = f"https://api.pugetsound.onebusaway.org/api/where/stops-for-route/40_2LINE.json?key={api_key}"
# Placeholders for future line 3 and line 4
url_3 = f"https://api.pugetsound.onebusaway.org/api/where/stops-for-route/40_3LINE.json?key={api_key}"
url_4 = f"https://api.pugetsound.onebusaway.org/api/where/stops-for-route/40_4LINE.json?key={api_key}"

if len(sys.argv) > 1:
    line_n = sys.argv[1]
else:
    line_n = input("Enter the line number: ")
match line_n:
    case "1":
        url = url_1
    case "2":
        url = url_2
    # case "3":
    #     url = url_3
    # case "4":
    #     url = url_4
    case "T" | "t":
        url = url_t
    case _:
        print("Invalid line number")
        sys.exit()

response = requests.get(url)
stops = []

if response.status_code == 200:
    data = json.loads(response.text)
    # print(data["data"]["references"]["stops"])
    for stop in data["data"]["references"]["stops"]:
        if stop["name"] not in stops:
            stops.append(stop["name"])
    print(f"{len(stops)} stops found")
    print(stops)
else:
    print("Error: ", response.status_code)
