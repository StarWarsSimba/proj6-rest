# Laptop Service

from flask import Flask, request, redirect, url_for, Response
from flask_restful import Resource, Api
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import json
import os
import acp_times
import math
from datetime import datetime
import config
import csv
import io

# Instantiate the app
app = Flask(__name__)
api = Api(app)

# Enable CORS for all routes - required when browser at :5002 fetches from :5001
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

client = MongoClient(
    os.environ.get('DB_PORT_27017_TCP_ADDR', 'db'),
    27017,
    serverSelectionTimeoutMS=3000,  # fail fast instead of hanging 30s
)
db = client.brevetdb

CONFIG = config.configuration()
app.secret_key = CONFIG.SECRET_KEY

def json_response(obj, status=200):
    return app.response_class(
        json.dumps(obj, default=str),
        mimetype='application/json',
        status=status,
    )
def csv_response(brevets, status=200):
    headings = ["brevets/distance", "brevets/begin_date", "brevets/begin_time"]
    rows = []
    max_controls = 0
    has_open = False
    has_close = False
    for brevet in brevets:
        if max_controls < len(brevet["controls"]):
            max_controls = len(brevet["controls"])
        row = [brevet["distance"], brevet["begin_date"], brevet["begin_time"]]
        for control in brevet["controls"]:
            row.append(control["km"])
            row.append(control["mi"])
            row.append(control["location"])
            if "open" in control:
                row.append(control["open"])
                has_open = True
            if "close" in control:
                row.append(control["close"])
                has_close = True
        rows.append(row)
    app.logger.debug("max_controls = %s" % max_controls)
    for i in range(max_controls):
        headings.append("brevets/controls/%s/km" % i)
        headings.append("brevets/controls/%s/mi" % i)
        headings.append("brevets/controls/%s/location" % i)
        if has_open:
            headings.append("brevets/controls/%s/open" % i)
        if has_close:
            headings.append("brevets/controls/%s/close" % i)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headings)
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=list.csv"},
    )


@app.route("/submit", methods=["POST"])
def submit_controls():
    brevet_distance = request.form.get("distance", type=int)
    if brevet_distance not in acp_times.VALID_DISTANCES:
        return redirect("http://localhost:5002/")

    begin_date = request.form.get("begin_date", "")
    begin_time = request.form.get("begin_time", "")
    datetime.strptime("{} {}".format(begin_date, begin_time), "%Y-%m-%d %H:%M")
    brevet_start = "{}T{}-00:00".format(begin_date, begin_time)

    miles_values = request.form.getlist("miles")
    km_values = request.form.getlist("km")
    locations = request.form.getlist("location")
    if not (len(miles_values) == len(km_values) == len(locations)):
        return redirect("http://localhost:5002/")
    document = {
        "distance": brevet_distance,
        "begin_date": begin_date,
        "begin_time": begin_time,
        "controls": []
    }

    for miles, km, location in zip(miles_values, km_values, locations):
        if not km.strip():
            continue
        control_km = float(km)
        if not math.isfinite(control_km) or not 0 <= control_km:
            return redirect("http://localhost:5002/")

        open_time = acp_times.open_time(control_km, brevet_distance, brevet_start)
        close_time = acp_times.close_time(control_km, brevet_distance, brevet_start)
        control = {
            "km": control_km,
            "location": location.strip(),
            "open": open_time,
            "close": close_time,
        }
        if miles.strip():
            control_miles = float(miles)
            if not math.isfinite(control_miles) or control_miles <= 0:
                return redirect("http://localhost:5002/")
            control["mi"] = control_miles
        document["controls"].append(control)

    if not document["controls"]:
        return redirect("http://localhost:5002/")

    db.brevets.insert_one(document)

    return redirect("http://localhost:5002/")


@app.route("/listAll")
@app.route("/listAll/json")
def list_all():
    brevets = list(db.brevets.find({}, {"_id": False}))
    return json_response({"brevets": brevets})


def list_times_only(time_field, is_json):
    brevets = []
    for brevet in db.brevets.find({}, {"_id": False}):
        result = {key: value for key, value in brevet.items() if key != "controls"}
        result["controls"] = [
            {
                key: value
                for key, value in control.items()
                if key != ("close" if time_field == "open" else "open")
            }
            for control in brevet.get("controls", [])
        ]
        brevets.append(result)
    if is_json:
        return json_response({"brevets": brevets})
    else:
        return csv_response(brevets)

@app.route("/listAll/csv")
def list_all_csv():
    brevets = list(db.brevets.find({}, {"_id": False}))
    app.logger.debug(type(brevets[0]))
    return csv_response(brevets)

@app.route("/listOpenOnly")
@app.route("/listOpenOnly/json")
def list_open_only():
    return list_times_only("open", True)

@app.route("/listOpenOnly/csv")
def list_open_only_csv():
    return list_times_only("open", False)

@app.route("/listCloseOnly")
@app.route("/listCloseOnly/json")
def list_close_only():
    return list_times_only("close", True)

@app.route("/listCloseOnly/csv")
def list_close_only_csv():
    return list_times_only("close", False)

@app.route("/_calc_times", methods=["GET", "OPTIONS"])
def _calc_times():
    """
    Calculates open/close times from miles, using rules
    described at https://rusa.org/octime_alg.html.
    Expects one URL-encoded argument, the number of miles.
    """
    if request.method == "OPTIONS":
        return json_response({})
    app.logger.debug("Got a JSON request")
    km = request.args.get('km', 999, type=float)
    brevet_distance = request.args.get('brevet_distance', 200, type=int)
    begin_date = request.args.get('begin_date', type=str)
    begin_time = request.args.get('begin_time', type=str)
    app.logger.debug("km={}".format(km))
    app.logger.debug("request.args: {}".format(request.args))
    if not begin_date or not begin_time:
        return json_response({"error": "begin_date and begin_time required"}, 400)
    try:
        open_time = acp_times.open_time(km, brevet_distance, begin_date + "T" + begin_time + "-00:00")
        close_time = acp_times.close_time(km, brevet_distance, begin_date + "T" + begin_time + "-00:00")
    except Exception as e:
        return json_response({"error": str(e)}, 400)
    result = {"open": open_time, "close": close_time}
    return json_response({"result": result})

# Run the application
if __name__ == '__main__':
    # threaded=True so one slow /controls query doesn't block /;
    # use_reloader=False so volume-mounted edits don't kill in-flight requests
    app.run(host='0.0.0.0', port=80, debug=True, threaded=True, use_reloader=False)
