#!/usr/bin/env python

# Prometheus Pingdom Exporter
# Require "PINGDOM_TOKEN" environment variable to authenticate with Pingdom API
# Listens on "PUBLISH_PORT" port which should be passed as an environment variable.
# Does not accept any parameters.
# Uses Token based authentication.


import os

import requests
import logging
from flask import Flask
from flask import Response
from jsonformatter import JsonFormatter


def get_data(url, headers):
    try:
        log_debug("Hitting the API" + url)
        r = requests.get(url, headers=headers)
        if not r.ok:
            log_error("Failed to get data from", url, str(r.status_code))
            return {}
    except requests.exceptions.ConnectionError as e:
        log_error("Failed to get data from" + url + str(e))
        return {}
    return r.json()


def format_metrics(met_name, met_val, labels=None):
    if labels is None:
        labels = {}
    if isinstance(met_val, list):
        met_val = len(met_val)
    if isinstance(met_val, bool):
        met_val = int(met_val)
    entry = "pingdom_check_" + met_name
    i = 1
    labels_len = len(labels)
    for k, v in labels.items():
        if i == 1:
            entry = entry + "{"
        entry = entry + ('%s="%s"' % (k, str(v)))
        if i != labels_len:
            entry = entry + ","
        else:
            entry = entry + "} "
        i = i + 1
    full_metric_string = entry + " " + str(met_val)
    log_debug(full_metric_string)
    return full_metric_string


def collector():
    all_metrics = []
    labels = {}
    status_map = {"up": 0, "unconfirmed_down": 1, "down": 2, "paused": -1, "unknown": -2}
    headers = {"Authorization": "Bearer " + os.environ.get("PINGDOM_TOKEN")}
    check_list = get_data("https://api.pingdom.com/api/3.1/checks?include_tags=true&include_severity=true", headers)

    if "checks" in check_list:
        for check in check_list["checks"]:
            region = env = None
            log_debug(check)
            value = status_map.get(check["status"])
            for tag in check["tags"]:
                if tag["name"] in ["east", "west", "global"]:
                    region = tag["name"]
                if tag["name"] in ["production", "pre-production"]:
                    env = tag["name"]
                labels = {
                    "id": check["id"],
                    "name": check["name"],
                    "resolution": check["resolution"],
                    "hostname": check["hostname"],
                    "severity": check["severity_level"].lower(),
                    "paused": "true" if value == -1 else "false"
                }
                if region:
                    labels["region"] = region
                if env:
                    labels["environment"] = env

            all_metrics.append(format_metrics("status", value, labels))
            value = check["lastresponsetime"]
            all_metrics.append(format_metrics("response_time", value, labels))

    all_metrics.append("")
    return all_metrics


if __name__ == "__main__":
    for ev in ["PUBLISH_PORT", "PINGDOM_TOKEN", "LOG_LEVEL"]:
        if ev == "LOG_LEVEL":
            LOG_LEVEL = os.environ.get("LOG_LEVEL", "warning").upper()
        elif not os.environ.get(ev):
            print("ERROR: Environment variable {} is not set".format(ev))
            exit(2)

    log_fmt = {
        "level": "levelname",
        "message": "message",
        "loggerName": "name",
        "threadName": "threadName",
        "timestamp": "asctime"
    }

    json_formatter = JsonFormatter(log_fmt)
    LOGGER = logging.getLogger()
    LOGGER.setLevel(LOG_LEVEL)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(LOG_LEVEL)
    stream_handler.setFormatter(json_formatter)
    LOGGER.addHandler(stream_handler)
    log_error = LOGGER.error
    log_warn = LOGGER.warning
    log_info = LOGGER.info
    log_debug = LOGGER.debug
    flask_log = logging.getLogger("werkzeug")
    flask_log.setLevel(logging.ERROR)
    flask_log.addHandler(stream_handler)

    my_app = Flask("Pingdom exporter")


    @my_app.route("/metrics", methods=["GET"])
    def get_metrics():
        metric_data = collector()
        if len(metric_data) > 1:
            return Response("\n".join(metric_data), mimetype="text/plain")
        else:
            return "No metrics collected", 404


    @my_app.route("/health", methods=["GET"])
    def health_check():
        return "", 200


    my_app.run(host="0.0.0.0", port=int(os.environ["PUBLISH_PORT"]), debug=True if LOG_LEVEL == "DEBUG" else False)
