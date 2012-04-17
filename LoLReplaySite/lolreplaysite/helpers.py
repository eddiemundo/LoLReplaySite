from lolreplaysite.constants import *
from pyramid.security import authenticated_userid
import struct, json, os, hashlib, uuid, re, logging
from GraphDatabase import GraphDatabase
log = logging.getLogger(__name__)

def get_hashed_password(password, salt):
	return hashlib.sha512(bytes(password + salt, 'utf-8')).hexdigest()

def get_parsed_replay_list(replay_nodes):
	"""Returns a list of dicts containing relevant replay info for a view""" 
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
		pov_champion_id = str(HEROES[team[pov_summoner_name]['champion_name'].lower()])
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
							'champion_id': str(HEROES[blue_team[summoner]['champion_name'].lower()]),
							'champion_name': blue_team[summoner]['champion_name'],
							} for summoner in blue_team],
				'purple_team': [
							{
							'summoner_name': summoner,
							'champion_id': str(HEROES[purple_team[summoner]['champion_name'].lower()]),
							'champion_name': purple_team[summoner]['champion_name'],
							} for summoner in purple_team],
				'filename': node.properties['filename']
				}
		replays.append(replay)
	return replays

def get_user(request):
	username = authenticated_userid(request)
	if username:
		g = GraphDatabase(DB_LOCATION).graph
		user_nodes = g.findNodesByProperty('type', 'user')
		user_node = g.findNodesByProperty('username', username, user_nodes)[0]
		return user_node.properties
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