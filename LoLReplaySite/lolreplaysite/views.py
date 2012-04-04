from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPFound
from pyramid.renderers import get_renderer

from datetime import datetime
from GraphDatabase import GraphDatabase
import struct, json, os
 

def site_layout():
	renderer = get_renderer("templates/main.pt")
	layout = renderer.implementation().macros['layout']
	return layout

@view_config(route_name='home', renderer='templates/main.pt')
def home(request):
	# view_config renderer is ignored
	return HTTPFound('/replays')

@view_config(route_name='news', renderer='templates/news.pt')
def news(request):
	return {'layout': site_layout(), 'active_tab': 'news', 'news_list': []}

@view_config(route_name='replays', renderer='templates/replays.pt')
def replays(request):
	gd = GraphDatabase(replay_database_filename)
	
	replay_list = []
	for node in gd.graph.nodes.values():
		datetime_uploaded = node.properties['date_uploaded']
		datetime_recorded = node.properties['date_recorded']
		replay = {
				'date_uploaded': datetime_uploaded.strftime("%a %d-%m-%y"),
				'date_recorded': datetime_recorded.strftime("%a %d-%m-%y"),
				'team1': [(summoner, str(heroes[hero.lower()])) for summoner, hero in node.properties['team1']],
				'team2': [(summoner, str(heroes[hero.lower()])) for summoner, hero in node.properties['team2']],
				'filename': node.name + '.lrf'
				}
		replay_list.append(replay)
	
	return {'layout': site_layout(), 'active_tab': 'replays', 'replay_list': replay_list}

@view_config(route_name='upload_a_replay', renderer='templates/upload_a_replay.pt')
def upload_a_replay(request):
	return {'layout': site_layout(), 'active_tab': 'upload_a_replay'}

@view_config(route_name='upload_replay')
def upload_replay(request):
	# check if a file was even uploaded
	if not hasattr(request.POST['replay'], 'file'):
		return HTTPFound('upload_a_replay')
	
	# get the json out of the replay file
	replay_file = request.POST['replay'].file
	
	# seek(0) stops my internet connection from crashing... don't ask me why
	replay_file.seek(0) 
	replay_file.seek(4)
	json_length = struct.unpack("<L", replay_file.read(4))[0]
	replay_data = json.loads(replay_file.read(json_length).decode('utf-8'))
	
	# parse the json for team information
	team1 = []
	team2 = []
	for player in replay_data['players']:
		if player['team'] == 1:
			team1.append((player['summoner'], player['champion']))
		elif player['team'] == 2:
			team2.append((player['summoner'], player['champion']))
	
	# open/create the replay database
	gd = GraphDatabase(replay_database_filename)
	
	# add and return a new replay node
	replay_node = gd.graph.addNode()
	
	# determine where we're going to save the uploaded replay file
	filename = replay_folder_path + replay_node.name + '.lrf'
	
	# put the replay data we care about into the replay node 
	replay_node.properties['date_uploaded'] = datetime.now()
	replay_node.properties['date_recorded'] = datetime.fromtimestamp(replay_data['timestamp'])
	replay_node.properties['filename'] = filename
	replay_node.properties['team1'] = team1
	replay_node.properties['team2'] = team2
	
	# save changes made to the database to disk
	gd.save()
	
	# write replay file to disk
	replay_file.seek(0)
	with open(filename, 'wb') as f:
		data = replay_file.read(2 << 16)
		while data:
			f.write(data)
			data = replay_file.read(2 << 16)

	return HTTPFound('/replays')

@view_config(route_name='download_replay')
def download_replay(request):
	# because of pyramids url routing replay_id and ext have no slashes in them
	replay_id = request.matchdict['id']
	ext = request.matchdict['ext']
	
	filename = replay_id + '.' + ext	

	response = Response(
					content_type='application/force-download',
					content_disposition='attachment; filename=' + filename
					)
	response.app_iter = open(replay_folder_path + filename, 'rb')
	response.content_length = os.path.getsize(replay_folder_path + filename)
	return response

replay_database_filename = 'lolreplaysite/databases/replays.gd'
replay_folder_path = 'lolreplaysite/replays/'
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