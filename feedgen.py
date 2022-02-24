#!/usr/bin/python3
#
# media.ccc.de Roku feed generator
#
# Copyright 2019 Ben Combee
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
# ------------------------------------
# 
# This takes a feed configuration file, fetches the feed information from the
# media.ccc.de API endpoints, and generates a Roku-compatible feed.json file
# that can be provided to Direct Publisher.
# 
# input is specified in config.yaml file.  See the version in the repo
# for options and documentation.

import sys
import re
import yaml
import json
from datetime import datetime, timezone
import requests
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache
import urllib
import langcodes
import textwrap

def read_config(config_filename):
	stream = open(config_filename, 'r')
	return yaml.safe_load(stream)

def process_recording(recording):
	output = {
		"dateAdded": recording["updated_at"],
		"videos": [
			{
				"url": recording["recording_url"],
				"quality": "HD",
				"videoType": "MP4"
			}
		],
		"duration": recording["length"],
		"language": langcodes.standardize_tag(recording["language"])
	}
	return output

slug_eventid_parser = re.compile(r"\w+-(\d+)-.*")

def process_event(event):
	episodeNumber = 0
	match = slug_eventid_parser.match(event["slug"])
	if (match):
		episodeNumber = int(match.group(1))

	output = {
		"id": event["guid"],
		"title": event["title"],
        "episodeNumber": episodeNumber,
        "releaseDate": event["release_date"],
        "credits": [],
        "content": {},
        "thumbnail": event["poster_url"],
        "shortDescription": textwrap.shorten(
        	event["subtitle"] or event["description"] or event["title"] or "No description provided",
        	width=200,
        	placeholder="..."),
        "longDescription": textwrap.shorten(
        	event["description"] or event["title"] or "No description provided",
        	width=500,
        	placeholder="...")
	}

	print("Loading event ", event["url"], file=sys.stderr)
	r = sess.get(event["url"])
	r.raise_for_status()
	event_data = r.json()

	for person in event_data["persons"]:
		output["credits"].append({
			"role": "actor",
			"name": person
			})

	for recording in event_data["recordings"]:
		if recording["language"] in languages \
		   and recording["folder"] == "h264-hd":
			output["content"] = process_recording(recording)
			break
	
	# don't allow items with no content
	if output["content"] == {}:
		raise RuntimeError

	return output

def process_conference(conf, languages, genres):
	print("Loading conf ", conf["url"], file=sys.stderr)
	r = sess.get(conf["url"])
	r.raise_for_status()
	conf_data = r.json()

	season = {
		"seasonNumber": 1,
		"episodes": []
	}

	output = { 
		"id":               conf_data["slug"],
		"title":            conf_data["title"],
		"genres":           genres,
		"tags":             conf["tags"],
		"thumbnail":        conf["thumbnail"],
		"releaseDate":      conf["releaseDate"],
		"shortDescription": conf["shortDescription"],
		"seasons": [ {
			"seasonNumber": 1,
			"episodes":     []
		} ]        
	}

	for event in conf_data["events"]:
		if event["original_language"] in languages:
			try:
				output["seasons"][0]["episodes"].append(process_event(event))
			except RuntimeError:
				print("Error: no content", file=sys.stderr)

	return output

#
# main program code
#

sess = CacheControl(requests.Session(),
                    cache=FileCache('.web_cache', forever=True))

config = read_config("configuration.yaml")

urlPrefix = config["apiroot"]
languages = config["languages"]
genres = config["genres"]

output = config["feedHeader"]
output["lastUpdated"] = datetime.now(timezone.utc).isoformat()
output["series"] = []

for conf in config["conferences"]:
	conf["url"] = urllib.parse.urljoin(urlPrefix, conf["url"])
	output["series"].append(
		process_conference(
			conf,
			languages,
			genres))

print(json.dumps(output, indent=2))