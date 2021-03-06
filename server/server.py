#!/usr/bin/env python

import flask, flask_cors, json, os, psycopg2, re, sys

app = flask.Flask(__name__)
flask_cors.CORS(app)

@app.before_request
def init():
	db_connect()
	setup_sessions()

def db_connect():
	default_dsn = 'dbname=us_congress'
	db_dsn = os.getenv('POSTGRES_DSN', default_dsn)
	flask.g.db = psycopg2.connect(db_dsn)

def setup_sessions():
	flask.g.sessions = {}
	cur = flask.g.db.cursor()
	cur.execute('''
		SELECT id, start_date, end_date
		FROM sessions
		ORDER BY id DESC
	''')

	rs = cur.fetchall()
	results = []
	if rs:
		for row in rs:
			id = row[0]
			flask.g.sessions[id] = {
				"start_date": str(row[1]),
				"end_date": str(row[2])
			}

@app.route("/")
def hello():
	return "Hello, you probably want to use: /pip, /districts, or /sessions"

@app.route("/pip")
def pip():

	lat = flask.request.args.get('lat', None)
	lng = flask.request.args.get('lng', None)
	min_session = flask.request.args.get('min_session', 0)
	min_session = int(min_session)

	columns = 'id, name, start_session, end_session, state, district_num, area, boundary_simple'
	include_geometry = flask.request.args.get('geometry', True)
	if include_geometry == '0':
		columns = columns.replace(', boundary_simple', '')

	if lat == None or lng == None:
		return "Please include 'lat' and 'lng' args."

	if not re.match('^-?\d+(\.\d+)?', lat):
		return "Please include a numeric 'lat'."

	if not re.match('^-?\d+(\.\d+)?', lng):
		return "Please include a numeric 'lng'."

	cur = flask.g.db.cursor()
	cur.execute('''
		SELECT {columns}
		FROM districts
		WHERE ST_within(ST_GeomFromText('POINT({lng} {lat})', 4326), boundary_geom)
		  AND (district_num > 0 OR at_large_only = 'Y')
		  AND end_session >= {min_session}
		ORDER BY end_session DESC
	'''.format(columns=columns, lat=lat, lng=lng, min_session=min_session))

	rs = cur.fetchall()
	results = []
	if rs:
		for row in rs:

			start_session = row[2]
			end_session = row[3]
			district_num = row[5]

			at_large = (district_num == 0)
			non_voting = (district_num == 98)

			result = {
				'id': row[0],
				'name': row[1],
				'start_session': start_session,
				'end_session': end_session,
				'start_date': flask.g.sessions[start_session]['start_date'],
				'end_date': flask.g.sessions[end_session]['end_date'],
				'state': row[4],
				'district_num': district_num,
				'area': row[6],
				'at_large': at_large,
				'non_voting': non_voting
			}

			if include_geometry != '0':
				result['boundary_simple'] = row[7]

			# Here is a weird edge case in TN, sessions 95-97, where 3 different
			# districts claim to include Memphis. We are favoring district 8,
			# but further research is needed to determine what happened.
			# (20180723/dphiffer)

			if row[4] == 'tn' and start_session == 95 and end_session == 97 and district_num != 8:
				continue

			results.append(result)

	cur.close()

	rsp = {
		'ok': 1,
		'results': results
	}
	return flask.jsonify(rsp)

@app.route("/districts")
def districts():

	ids = flask.request.args.get('ids', None)

	if ids == None:
		return "Please include 'ids' arg (hyphen- or comma-separated numeric IDs)."
	if not re.match('^\d+(,\d+)*$', ids) and not re.match('^\d+(-\d+)*$', ids):
		return "Invalid 'ids' arg: use hyphen- or comma-separated numeric IDs."

	if re.match('^\d+(-\d+)*$', ids):
		ids = ids.replace('-', ',')

	cur = flask.g.db.cursor()
	cur.execute('''
		SELECT id, name, start_session, end_session, state, district_num, area, boundary_simple
		FROM districts
		WHERE id IN ({ids})
		ORDER BY end_session DESC
	'''.format(ids=ids))

	rs = cur.fetchall()
	results = []
	if rs:
		for row in rs:

			start_session = row[2]
			end_session = row[3]
			district_num = row[5]

			at_large = (district_num == 0)
			non_voting = (district_num == 98)

			results.append({
				'id': row[0],
				'start_session': start_session,
				'end_session': end_session,
				'start_date': flask.g.sessions[start_session]['start_date'],
				'end_date': flask.g.sessions[end_session]['end_date'],
				'state': row[4],
				'district_num': district_num,
				'area': row[6],
				'at_large': at_large,
				'non_voting': non_voting,
				'boundary_simple': row[7]
			})

	cur.close()

	rsp = {
		'ok': 1,
		'results': results
	}
	return flask.jsonify(rsp)

@app.route("/sessions")
def sessions():
	rsp = {
		'ok': 1,
		'results': flask.g.sessions
	}
	return flask.jsonify(rsp)

if __name__ == '__main__':
	port = os.getenv('PORT', 5000)
	port = int(port)
	app.run(host='0.0.0.0', port=port)
