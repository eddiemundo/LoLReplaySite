from lolreplaysite.constants import *
from pyramid.security import authenticated_userid
import struct, json, os, hashlib, uuid, re, logging
from graphdatabase import GraphDatabase
log = logging.getLogger(__name__)

def suffix(d):
    return 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')

def custom_strftime(format, t):
    return t.strftime(format).replace('{S}', str(t.day) + suffix(t.day))

def get_hashed_password(password, salt):
	return hashlib.sha512(bytes(password + salt, 'utf-8')).hexdigest()

def get_replays(replay_nodes):
	replays = []
	for replay_node in replay_nodes:
		pov_summoner_name = replay_node.pov
		pov_champion_name = None
		pov_champion_id = None
		blue_team = []
		purple_team = []
		for team, result in ((replay_node.blue_team, blue_team),
							(replay_node.purple_team, purple_team)):
			for player in team:
				if player['summoner_name'] == pov_summoner_name:
					pov_champion_name = player['champion_name']
					pov_champion_id = str(HEROES[pov_champion_name.lower()])
				player_data = {
							'summoner_name': player['summoner_name'],
							'champion_name': player['champion_name'],
							'champion_id': player['champion_id'],
							}
				result.append(player_data)
		replay = {
				'id': replay_node.id,
				'title': replay_node.title,
				'length': "{0}:{1}:{2}".format(replay_node.length//3600,
											replay_node.length//60,
											replay_node.length % 60),
				'date_recorded': replay_node.date_recorded.strftime("%a %d-%m-%y"),
				'pov_summoner_name': pov_summoner_name,
				'pov_champion_name': pov_champion_name,
				'pov_champion_id': pov_champion_id,
				'blue_team': blue_team,
				'purple_team': purple_team,
				'filename': replay_node.filename,
				}
		replays.append(replay)
	return replays


class stupid(object):
	db = None

def get_user(request):
	username = authenticated_userid(request)
	if username:
		stupid.db = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = stupid.db.graph
		user = g.node(type='user', username=username)
		return user.properties
	else:
		return None

def user_menu_items(request):
	menu_items = USER_MENU_ITEMS
	result_menu_items = []
	user = get_user(request)
	# if there is no authenticated user
	if not user:
		return result_menu_items
	user_map = {'userid': user['userid'], 'username': user['username']}
	for menu_item in menu_items:
		result_menu_item = dict(menu_item)
		menu_items_helper(request, menu_item)
		# notifications also needs img data
		if menu_item['name'] == 'Notifications':
			icon_url = 'lolreplaysite:static/orange_mail_icon_small.png'
			src_map = {'mail_icon': request.static_url(icon_url)}
			result_menu_item['src'] = menu_item['src'].format_map(src_map)
		result_menu_item['href'] = menu_item['href'].format_map(user_map)
		# add menu item to the list we will eventually return
		result_menu_items.append(result_menu_item)
	return result_menu_items
	
def main_menu_items(request):
	menu_items = MAIN_MENU_ITEMS
	for menu_item in menu_items:
		menu_items_helper(request, menu_item)
	return menu_items

def menu_items_helper(request, menu_item):
	route_matched = request.matched_route.match(menu_item['href'])
	if route_matched != None:
		menu_item['active'] = True
	else:
		menu_item['active'] = False