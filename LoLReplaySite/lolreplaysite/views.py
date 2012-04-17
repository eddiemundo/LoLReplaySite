from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPFound, HTTPForbidden
from pyramid.renderers import get_renderer
from pyramid.security import remember, forget, authenticated_userid

from GraphDatabase import GraphDatabase
from lolreplaysite.helpers import *
from lolreplaysite.constants import REPLAY_FOLDER_LOCATION, DB_LOCATION

import struct, json, os, hashlib, uuid, re, logging
from datetime import datetime

log = logging.getLogger(__name__)

class View(object):
	def __init__(self, request):
		self.request = request
		renderer = get_renderer("templates/main.pt")
		layout = renderer.implementation().macros['layout']
		self.layout = layout 
		self.user_menu_items = user_menu_items(request)
		self.main_menu_items = main_menu_items(request)
		self.logged_in = authenticated_userid(request)
	
	@view_config(route_name='replays', renderer='templates/replays.pt')
	def replays(self):
		g = GraphDatabase(DB_LOCATION).graph
		replay_nodes = g.findNodesByProperty('type', 'replay')
		return {
			'replay_list': get_parsed_replay_list(replay_nodes),
			}
	
	@view_config(route_name='faq')
	def faq(self):
		return {}
	
	@view_config(route_name='feedback')
	def feedback(self):
		return {}
	
	@view_config(route_name='user_notifications')
	def user_notifications(self):
		return {}
		
	@view_config(route_name='user_replays', renderer='templates/replays.pt')
	def user_replays(self):
		userid = int(self.request.matchdict['userid'])
		g = GraphDatabase(DB_LOCATION).graph
		nodes = g.nodes
		replay_nodes = []
		if userid in nodes:
			replay_nodes = list(g.search(userid, {'outgoing': ['owns']}))		
		return {
			'replay_list':get_parsed_replay_list(replay_nodes),
			}
	
	@view_config(route_name='user_reviews')
	def user_reviews(self):
		return {}
		
	@view_config(route_name='user_account')
	def user_account(self):
		return {}
	
	@view_config(route_name='upload', renderer='templates/upload.pt')
	def upload(self):
		if not self.logged_in:
			self.request.session['came_from'] = '/upload'
			return HTTPFound(self.request.route_url('login'))
		return {}
	
@view_config(route_name='upload_replay', request_method='POST')
def upload_replay(request):
	# check if a file was even uploaded
	if not hasattr(request.POST['replay'], 'file'):
		return HTTPFound(request.route_url('upload'))
	
	# the replay file that was uploaded
	replay_file = request.POST['replay'].file
	# seek(0) stops my internet connection from crashing... don't ask me why
	replay_file.seek(0)
	# skip the first 4 bytes 
	replay_file.seek(4)
	# read the next 4 bytes. this is the length of the json header
	json_length = struct.unpack("<L", replay_file.read(4))[0]
	# load the json data into python form
	replay_data = json.loads(replay_file.read(json_length).decode('utf-8'))
	
	# parse the json for specific replay, team, and player data
	pov = None
	blue_team = {}
	purple_team = {}
	for player in replay_data['players']:
		# find out who's pov it is 
		if replay_data['accountID'] == player['accountID']:
			pov = player['summoner']
		# parse the items for the player
		items = []
		for item in ('item1', 'item2', 'item3', 'item4', 'item5', 'item6'):
			if item in player:
				items.append(item)
			else:
				items.append(None)
				
		def getPlayer(attribute):
			"""Returns 0 if attribute doesn't exist"""
			if attribute in player:
				return player[attribute]
			else:
				return 0
		# put all the player data into one dictionary
		player_data = {
					'champion_name': player['champion'],
					'level': player['level'],
					'kills': getPlayer('kills'),
					'deaths': getPlayer('deaths'),
					'assists': getPlayer('assists'),
					'items': tuple(items),
					'summoner_spells': (player['spell1'], player['spell2']),
					'gold': getPlayer('gold'),
					'lane_minions_killed': getPlayer('minions'),
					'neutral_minions_killed': getPlayer('neutralMinionsKilled'),
					}
		team = None
		if player['team'] == 1:
			team = blue_team
		elif player['team'] == 2:
			team = purple_team
		team[player['summoner']] = player_data
				
	# open/create the replay database
	gd = GraphDatabase(DB_LOCATION)
	# most of the replay properties
	title = request.POST['title']
	if not title:
		title = replay_data['name']
	replay_properties = {
						'type': 'replay',
						'title': title,
						'description': request.POST['description'],
						'length': replay_data['matchLength'],
						'pov': pov,
						'client_version': replay_data,
						'recorder_version': None,
						'date_recorded': datetime.fromtimestamp(replay_data['timestamp']),
						'date_uploaded': datetime.now(),
						'blue_team': blue_team,
						'purple_team': purple_team,
						}
	
	# add a new replay node to the graph return it
	replay_node = gd.graph.addNode(properties=replay_properties)
	
	# put the filename, and location into the replay node
	filename = str(replay_node.id) + '.lrf'
	location = REPLAY_FOLDER_LOCATION + filename
	 
	replay_node.properties['filename'] = filename
	replay_node.properties['location'] = location
	
	# relate this replay node to the user node that uploaded it
	user_node = gd.graph.findNodesByProperty('username', authenticated_userid(request))[0]
	gd.graph.relate(user_node.id, 'owns', replay_node.id)
	
	# write replay file to disk
	replay_file.seek(0)
	with open(location, 'wb') as f:
		data = replay_file.read(2 << 16)
		while data:
			f.write(data)
			data = replay_file.read(2 << 16)

	# save changes made to the database to disk
	gd.save()

	return HTTPFound('/replays')

@view_config(route_name='download_replay')
def download_replay(request):
	filename = request.matchdict['id'] + '.' + request.matchdict['ext']	
	response = Response(
					content_type='application/force-download',
					content_disposition='attachment; filename=' + filename,
					)
	response.app_iter = open(REPLAY_FOLDER_LOCATION + filename, 'rb')
	response.content_length = os.path.getsize(REPLAY_FOLDER_LOCATION + filename)
	return response
	
@view_config(route_name='register', renderer='templates/register.pt')
def register(self, request):
	error_message = ''
	username = ''
	email_address = ''
	password = ''
	came_from = '/replays'
	
	# see where the user came from
	session = request.session
	if 'came_from' in session:
		came_from = session['came_from']
	
	if 'form.submitted' in request.params:
		username = request.params['username']
		email_address = request.params['email_address']
		password = request.params['password']
		# open/create the database containing our user nodes
		gd = GraphDatabase(DB_LOCATION)
		user_nodes = gd.graph.findNodesByProperty('type', 'user')
		
		if len(username) < 3:
			error_message = 'Username needs to be 3 or more characters'
		elif gd.graph.findNodesByProperty('username', username, user_nodes):
			error_message = 'Username is already taken'
		elif not re.match(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:[A-Z]{2}|com|org|net|edu|gov|mil|biz|info|mobi|name|aero|asia|jobs|museum)\b", email_address):
			error_message = 'Email address is not valid'
			email_address = ''
		elif gd.graph.findNodesByProperty('email_address', email_address, user_nodes):
			error_message = 'Email address is already taken'
			email_address = ''
		elif len(password) < 3:
			password = 'Password needs to be 3 or more characters'
			password_repeated = ''
		else:
			salt = uuid.uuid4().hex
			hashed_password = hashlib.sha512(bytes(password + salt, 'utf-8')).hexdigest()
			user_properties = {
							'type': 'user',
							'username': username,
							'email_address': email_address,
							'password': hashed_password,
							'salt': salt,
							'date_registered': datetime.now(),
							}
			user_node = gd.graph.addNode(properties=user_properties)
			user_node.properties['userid'] = user_node.id
			gd.save()
			
			# authenticate the newly registered user
			headers = remember(request, username)
			return HTTPFound(location=came_from, headers=headers)
	
	return {
		'page_title': 'Registration',
		'error_message': error_message,
		'url': request.application_url + '/register',
		'username': username,
		'email_address': email_address,
		'password': password,
		'came_from': came_from,
		}

@view_config(route_name='login', renderer="templates/login.pt", context=HTTPForbidden)
@view_config(route_name='login', renderer="templates/login.pt")
def login(self, request):
	message = ''
	username = ''
	password = ''
	came_from = '/replays'
	
	# see where the user came from
	session = request.session
	if 'came_from' in session:
		came_from = session['came_from']
	
	if 'form.submitted' in request.params:
		username = request.params['username']
		password = request.params['password']
		came_from = request.params['came_from']
		# open/create our userdb
		usersdb = GraphDatabase(DB_LOCATION)
		users_graph = usersdb.graph
		possible_users = users_graph.findNodesByProperty('username', username)
		        
		if len(possible_users) == 1:
			user = possible_users[0]
			user_password = user.properties['password']
			user_salt = user.properties['salt']
			if get_hashed_password(password, user_salt) == user_password:
				headers = remember(request, username)
				return HTTPFound(location=came_from, headers=headers)
		
		message = 'Username or password is incorrect'
		login = ''
		password = ''

	return {
		"page_title": "Login",
		"message": message,
		"url": request.application_url + '/login',
		'came_from': came_from,
		'username': username,
		"password": password,
	    }

@view_config(route_name='logout')
def logout(self, request):
    headers = forget(request)
    return HTTPFound(location='/replays', headers=headers)
   