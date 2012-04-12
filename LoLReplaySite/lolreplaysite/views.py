from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPFound, HTTPForbidden
from pyramid.renderers import get_renderer

from pyramid.security import has_permission, remember, forget, authenticated_userid, unauthenticated_userid, effective_principals

from datetime import datetime
from GraphDatabase import GraphDatabase
from lolreplaysite.security import db_location
import struct, json, os, hashlib, uuid, re, logging
from collections import defaultdict

log = logging.getLogger(__name__)



def site_layout():
	renderer = get_renderer("templates/main.pt")
	layout = renderer.implementation().macros['layout']
	return layout

@view_config(route_name='home', renderer='templates/home.pt')
def home(request):
	return {
		'layout': site_layout(),
		'active_tab': 'Home',
		'news_list': [],
		'logged_in': authenticated_userid(request),
		}

@view_config(route_name='replays', renderer='templates/replays.pt')
def replays(request):
	gd = GraphDatabase(db_location)
	replay_nodes = gd.graph.findNodesByProperty('type', 'replay')
	replays = []
	# code is a bit sloppy
	for node in replay_nodes:
		length = node.properties['length']
		blue_team = node.properties['blue_team']
		purple_team = node.properties['purple_team']
		pov_summoner_name = node.properties['pov']
		pov_champion_id = ''
		pov_champion_name = ''
		team = None
		if pov_summoner_name in blue_team:
			team = blue_team
		elif pov_summoner_name in purple_team:
			team = purple_team
		pov_champion_id = str(heroes[team[pov_summoner_name]['champion_name'].lower()])
		pov_champion_name = team[pov_summoner_name]['champion_name']
			
		replay = {
				'pov': {
					'summoner_name': pov_summoner_name,
					'champion_id': pov_champion_id,
					'champion_name': pov_champion_name,
					},
				'title': node.properties['title'],
				'length': "{0}:{1}:{2}".format(length//3600, length//60, length % 60),
				'date_recorded': node.properties['date_recorded'].strftime("%a %d-%m-%y"),
				'blue_team': [
							{
							'summoner_name': summoner,
							'champion_id': str(heroes[blue_team[summoner]['champion_name'].lower()]),
							'champion_name': blue_team[summoner]['champion_name'],
							} for summoner in blue_team],
				'purple_team': [
							{
							'summoner_name': summoner,
							'champion_id': str(heroes[purple_team[summoner]['champion_name'].lower()]),
							'champion_name': purple_team[summoner]['champion_name'],
							} for summoner in purple_team],
				'filename': node.properties['filename']
				}
		replays.append(replay)
	return {
		'layout': site_layout(),
		'replay_list': replays,
		'active_tab': 'Replays',
		'logged_in': authenticated_userid(request),
		}

@view_config(route_name='faq')
def faq(request):
	return HTTPFound('/')

@view_config(route_name='feedback')
def feedback(request):
	return HTTPFound('/')

@view_config(route_name='upload', renderer='templates/upload.pt')
def upload(request):
	logged_in = authenticated_userid(request)
	if not logged_in:
		request.session['came_from'] = '/upload'
		return HTTPFound(request.route_url('login'))
	return {
		'layout': site_layout(),
		'active_tab': 'Upload',
		'logged_in': logged_in
		}

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
	gd = GraphDatabase(db_location)
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
	location = replay_folder_location + filename
	 
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
	response.app_iter = open(replay_folder_location + filename, 'rb')
	response.content_length = os.path.getsize(replay_folder_location + filename)
	return response


@view_config(route_name='register', renderer='templates/register.pt')
def register(self, request):
	error_message = ''
	username = ''
	email_address = ''
	password = ''
	came_from = '/'
	
	# see where the user came from
	session = request.session
	if 'came_from' in session:
		came_from = session['came_from']
	
	if 'form.submitted' in request.params:
		username = request.params['username']
		email_address = request.params['email_address']
		password = request.params['password']
		# open/create the database containing our user nodes
		gd = GraphDatabase(db_location)
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
			gd.graph.addNode(properties=user_properties)
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
	came_from = '/'
	
	# see where the user came from
	session = request.session
	if 'came_from' in session:
		came_from = session['came_from']
	
	if 'form.submitted' in request.params:
		username = request.params['username']
		password = request.params['password']
		came_from = request.params['came_from']
		# open/create our userdb
		usersdb = GraphDatabase(db_location)
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
   


replay_folder_location = 'lolreplaysite/replays/'
heroes = {
    'ahri':103,
    'akali':84,
    'alistar':12,
    'amumu':32,
    'anivia':34,
    'annie':1,
    'ashe':22,
    'blitzcrank':53,
    'brand':63,
    'caitlyn':51,
    'cassiopeia':69,
    "chogath":31,
    "corki":42,
    'drmundo':36,
    'evelynn':28,
    'ezreal':81,
    'fiddlesticks':9,
    'fiora':114,
    'fizz':105,
    'galio':3,
    'gangplank':41,
    'garen':86,
    'gragas':79,
    'graves':104,
    'heimerdinger':74,
    'irelia':39,
    'janna':40,
    'jarvaniv':59,
    'jax':24,
    'karma':43,
    'karthus':30,
    'kassadin':38,
    'katarina':55,
    'kayle':10,
    'kennen':85,
    "kogmaw":96,
    'leblanc':7,
    'leesin':64,
    'leona':89,
    'lulu':117,
    'lux':99,
    'malphite':54,
    'malzahar':90,
    'maokai':57,
    'masteryi':11,
    'missfortune':21,
    'mordekaiser':82,
    'morgana':25,
    'nasus':75,
    'nautilus':111,
    'nidalee':76,
    'nocturne':56,
    'nunu':20,
    'olaf':2,
    'orianna':61,
    'pantheon':80,
    'poppy':78,
    'rammus':33,
    'renekton':58,
    'riven':92,
    'rumble':68,
    'ryze':13,
    'sejuani':113,
    'shaco':34,
    'shen':98,
    'shyvana':102,
    'singed':27,
    'sion':14,
    'sivir':15,
    'skarner':72,
    'sona':37,
    'soraka':16,
    'swain':50,
    'talon':91,
    'taric':44,
    'teemo':17,
    'tristana':18,
    'trundle':48,
    'tryndamere':23,
    'twisted fate':4,
    'twitch':29,
    'udyr':77,
    'urgot':6,
    'vayne':67,
    'veigar':45,
    'viktor':112,
    'vladimir':8,
    'volibear':106,
    'warwick':19,
    'wukong':62,
    'xerath':101,
    'xinzhao':5,
    'yorick':83,
    'ziggs':115,
    'zilean':26,
}
heroes = defaultdict(int, heroes)

# helper functions
def get_hashed_password(password, salt):
	return hashlib.sha512(bytes(password + salt, 'utf-8')).hexdigest()