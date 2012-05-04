from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPFound, HTTPForbidden, HTTPNotFound
from pyramid.renderers import get_renderer
from pyramid.security import remember, forget, authenticated_userid

from graphdatabase import GraphDatabase
from lolreplaysite.helpers import *
from lolreplaysite.constants import REPLAY_FOLDER_LOCATION, DB_LOCATION
from lolreplaysite.constants import HOST, PORT, HEROES
from lolreplaysite.macros import *


from collections import Counter
import struct, json, os, hashlib, uuid, re, logging
from datetime import datetime
import copy
from pyramid.exceptions import NotFound

log = logging.getLogger(__name__)

class BaseView(object):
	def __init__(self, request):
		renderer = get_renderer('templates/macros/base_macro.pt')
		self.base_macro = renderer.implementation().macros['base_macro']
		request.session['came_from'] = request.current_route_url()
		self.request = request
		self.logged_in = authenticated_userid(request)
		# TODO: replace these URLs with request.route_url()
		self.user_menu_items = (
							{
							'label': 'Your Replay Stuff',
							'href': request.route_url('your_replays'),
							},
							{
							'label': 'Your Review Stuff',
							'href': request.route_url('yourreviewstuff-reviewsaskedofyou'),
							}
							)
		self.main_menu_items = (
							{
							'label': 'Replays',
							'href': request.route_url('replays'),
							},
							{
							'label': 'FAQ',
							'href': '#',
							},
							{
							'label': 'Feedback',
							'href': '#',
							},
							{
							'label': 'Upload',
							'href': request.route_url('upload'),
							}
							)

	@view_config(route_name='test', renderer='templates/test.pt')
	def test(self):
		return {}

	@view_config(route_name='upload', renderer='templates/upload.pt')
	def upload(self):
		if not self.logged_in:
			self.request.session['came_from'] = '/upload'
			return HTTPFound(self.request.route_url('login'))
		return {}


class ReplaysView(BaseView):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replays_macro.pt')
		self.replays_macro = renderer.implementation().macros['replays_macro']

	def get_replays(self, replay_nodes):
		replays = []
		for replay_node in replay_nodes:
			pov_summoner_name = replay_node.pov
			replay = {
					'title': replay_node.title,
					'date_recorded': replay_node.date_recorded.strftime("%a %d-%m-%y"),
					'pov_summoner_name': pov_summoner_name,
					'length': "{0}:{1}:{2}".format(replay_node.length // 3600,
												replay_node.length // 60,
												replay_node.length % 60),
					'id': replay_node.id,
					'filename': replay_node.filename,
					'teams': [],
					'num_comments': len(replay_node.adjacent_nodes('owns', 'outgoing', type='comment')),
					'num_reviews': len(replay_node.adjacent_nodes('owns', 'outgoing', type='review')),
					}
			for team in (replay_node.blue_team, replay_node.purple_team):
				t = []
				for player in team:
					player_summoner_name = player['summoner_name']
					player_champion_name = player['champion_name']
					player_champion_id = str(HEROES[player_champion_name.lower()])
					if player_summoner_name == pov_summoner_name:
						replay['pov_champion_name'] = player_champion_name
						replay['pov_champion_id'] = player_champion_id
					player_data = {
								'summoner_name': player_summoner_name,
								'champion_name': player_champion_name,
								'champion_id': player_champion_id,
								}
					t.append(player_data)
				replay['teams'].append(t)
			replays.append(replay)
		return replays

	@view_config(route_name='replays', renderer='templates/replays.pt')
	def replays(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		replay_nodes = g.nodes(type='replay')
		return {'replays': self.get_replays(replay_nodes)}

	@view_config(route_name='your_replays', renderer='templates/your_replays.pt')
	def your_replays(self):
		if not self.logged_in:
			return HTTPFound(self.request.route_url('replays'))

		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		user_node = g.node(type='user', username=self.logged_in)
		
		replay_nodes = user_node.adjacent_nodes('owns', 'outgoing', type='replay')
		return {'replays': self.get_replays(replay_nodes), }

class ReplayView(BaseView):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replay_macro.pt')
		self.replay_macro = renderer.implementation().macros['replay_macro']

	def get_replay_details(self, replay_node):
		replay = replay_node
		if replay is not None:
			l = replay.length
			return {
				'replay_id': replay.id,
				'length': "{0}:{1}:{2}".format(l // 3600, l // 60, l % 60),
				'client_version': replay.client_version,
				'recorder_version': replay.recorder_version,
				'pov': replay.pov,
				'description': replay.description,
				'title': replay.title,
				'teams': (copy.deepcopy(replay.blue_team), copy.deepcopy(replay.purple_team)),
				}

	def get_comments(self, replay_node):
		comment_nodes = replay_node.adjacent_nodes('owns',
													'outgoing',
													type='comment')
		comments = []
		for comment_node in comment_nodes:
			dt = comment_node.datetime
			ampm = 'am' if dt.hour < 12 else 'pm'
			hour = None
			if dt.hour < 1:
				hour = '12'
			elif 1 <= dt.hour < 13:
				hour = str(dt.hour)
			elif 13 <= dt.hour < 24:
				hour = str(dt.hour % 12)
			else:
				hour = '12'
			comments.append({'name': comment_node.name,
						'comment': comment_node.comment,
						'datetime': custom_strftime('%B {S}, %Y ' + hour + ':%M' + ampm, comment_node.datetime)
						})
		return comments

	def get_reviews(self, replay_node):
		review_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type='review')
		return tuple(review_nodes)

	def diff(self, l1, l2):
		c1 = Counter(l1)
		c2 = Counter(l2)
		d = c1 - c2
		return tuple(d.elements())

	@view_config(route_name='replay', renderer='templates/replay.pt')
	def replay(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		replay_id = int(self.request.matchdict['replay_id'])
		replay_node = g.node(replay_id, type='replay')
		if replay_node is None:
			return HTTPFound(self.request.route_url('replays'))
		template_dict = self.get_replay_details(replay_node)
		template_dict['comments'] = self.get_comments(replay_node)
		return template_dict

	@view_config(route_name='comment_on_replay')
	def comment_on_replay(self):
		return {}

class YourReplayStuffReplaysReplay_id(BaseView):
	route_name = 'yourreplaystuff-replays-replay_id-{}'
	template_name = 'templates/{}.pt'.format(route_name)

	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replay_macro.pt')
		self.replay_macro = renderer.implementation().macros['replay_macro']
		renderer = get_renderer('templates/macros/comments.pt')
		self.comments_macro = renderer.implementation().macros['comments']

		self.gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		self.g = self.gd.graph

	def get_replay_info(self, replay_node):
		replay = replay_node
		if replay is not None:
			l = replay.length
			return {
				'replay_id': replay.id,
				'length': "{0}:{1}:{2}".format(l // 3600, l // 60, l % 60),
				'client_version': replay.client_version,
				'recorder_version': replay.recorder_version,
				'pov': replay.pov,
				'description': replay.description,
				'title': replay.title,
				'teams': (copy.deepcopy(replay.blue_team), copy.deepcopy(replay.purple_team)),
				}

	def get_replay_comments(self, replay_node):
		comment_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type='comment')
		comments = []
		for comment_node in comment_nodes:
			dt = comment_node.datetime
			ampm = 'am' if dt.hour < 12 else 'pm'
			hour = None
			if dt.hour < 1:
				hour = '12'
			elif 1 <= dt.hour < 13:
				hour = str(dt.hour)
			elif 13 <= dt.hour < 24:
				hour = str(dt.hour % 12)
			else:
				hour = '12'
			comments.append({'name': comment_node.name,
						'comment': comment_node.comment,
						'datetime': custom_strftime('%B {S}, %Y ' + hour + ':%M' + ampm, comment_node.datetime)
						})
		return comments

	def get_replay_reviews(self, replay_node):
		review_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type='review')
		return tuple(review_nodes)

	def get_reviewers(self, replay_node):
		# get all usernames except current user
		all_usernames = []
		user_nodes = self.g.nodes(type='user')
		for user_node in user_nodes:
			if user_node.username != self.logged_in:
				all_usernames.append(user_node.username)

		# get usernames of users that have reviewed this replay
		review_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type="review")
		reviewer_usernames = []
		for review_node in review_nodes:
			reviewer_node = review_node.adjacent_node('owns', 'incoming', type='user')
			reviewer_usernames.append(reviewer_node.username)
		
		# get usernames of users that have already been asked to review
		askees = replay_node.adjacent_nodes('asked_to_review', 'incoming', type='user')
		askee_usernames = []
		for askee in askees:
			askee_usernames.append(askee.username)
		
		users_minus_reviewer_names = self.diff(all_usernames, reviewer_usernames)
		eligible_reviewers = self.diff(users_minus_reviewer_names, askee_usernames)
		
		# return reviewers and eligible reviewers usernames
		return reviewer_usernames, eligible_reviewers

	def diff(self, l1, l2):
		c1 = Counter(l1)
		c2 = Counter(l2)
		d = c1 - c2
		return tuple(d.elements())

	@view_config(route_name=route_name.format('comments'),
				renderer=template_name.format('comments'))
	def comments(self):
		replay_id = int(self.request.matchdict['replay_id'])
		replay_node = self.g.node(replay_id, type='replay')
		if replay_node is None:
			raise HTTPNotFound

		template_variables = self.get_replay_info(replay_node)
		template_variables['comments'] = self.get_replay_comments(replay_node)
		template_variables['num_reviews'] = len(self.get_replay_reviews(replay_node))

		return template_variables

	@view_config(route_name=route_name.format('reviews'),
				renderer=template_name.format('reviews'))
	def reviews(self):
		replay_id = int(self.request.matchdict['replay_id'])
		replay_node = self.g.node(replay_id, type='replay')
		if replay_node is None:
			raise HTTPNotFound

		template_variables = self.get_replay_info(replay_node)
		if 'owner_comment' in  replay_node.properties:
			template_variables['owner_comment'] = replay_node.owner_comment
		else:
			template_variables['owner_comment'] = None
		template_variables['comments'] = self.get_replay_comments(replay_node)
		template_variables['reviews'] = self.get_replay_reviews(replay_node)
		template_variables['num_reviews'] = len(template_variables['reviews'])
		template_variables['not_reviewed_msg'] = 'This replay has not been reviewed yet.'
		reviewer_usernames, askable_usernames = self.get_reviewers(replay_node)
		template_variables['askable_usernames'] = askable_usernames
		template_variables['reviewer_usernames'] = reviewer_usernames

		return template_variables

class YourReviewStuff(BaseView):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/your-review-stuff.pt')
		self.your_review_stuff_macro = renderer.implementation().macros['your-review-stuff']

	@view_config(route_name='yourreviewstuff-reviewsaskedofyou',
				renderer='templates/yourreviewstuff-reviewsaskedofyou.pt')
	def reviews_asked_of_you(self):
		# Gets asker names and the info of the respective replays they want you
		# to review puts them into a tuple pairs and sends that to the template
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph

		if not self.logged_in:
			log.debug('your-review-stuff/reviews-asked-of-you: user is not logged in')
			raise HTTPNotFound

		user = g.node(type='user', username=self.logged_in)
		if user is None:
			log.debug('your-review-stuff/reviews-asked-of-you: username does not exist')
			raise HTTPNotFound
		replays = user.adjacent_nodes('asked_to_review', 'outgoing', type='replay')
		askers_info = []
		replays_info = []
		for replay in replays:
			replay_info = {
						'id': replay.id,
						'title': replay.title,
						}
			replays_info.append(replay_info)
			asker = replay.adjacent_node('owns', 'incoming', type='user')
			if asker is None:
				log.debug('your-review-stuff/reviews-asked-of-you: asker does not exist')
				raise HTTPNotFound
			asker_info = {'username': asker.username}
			askers_info.append(asker_info)

		return {
			'askers_and_replays': tuple(zip(askers_info, replays_info))
			}
	
	@view_config(route_name='yourreviewstuff-reviewsaskedofothers',
				renderer='templates/yourreviewstuff-reviewsaskedofothers.pt')
	def reviews_asked_of_others(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		if not self.logged_in:
			log.debug('your-review-stuff/reviews-asked-of-others: user is not logged in')
			raise HTTPNotFound
		user = g.node(type='user', username=self.logged_in)
		if user is None:
			log.debug('your-review-stuff/reviews-asked-of-others: username does not exist')
			raise HTTPNotFound
		replays = user.adjacent_nodes('owns', 'outgoing', type='replay')
		askee_infos = []
		replay_infos = []
		for replay in replays:
			askees = replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
			for askee in askees:
				askee_info = {'username': askee.username}
				replay_info = {'id': replay.id,
							'title': replay.title}
				askee_infos.append(askee_info)
				replay_infos.append(replay_info)
		return {'askers_and_replays': tuple(zip(askee_infos, replay_infos))}
		
class LoginView(object):
	def __init__(self, request):
		self.request = request
		self.came_from = request.route_url('test')
		if 'came_from' in request.session:
			self.came_from = request.session['came_from']

	@view_config(route_name='login', renderer='templates/login.pt')
	def login(self):
		request = self.request
		if 'form' in request.params:
			username = request.params['username']
			password = request.params['password']
			gd = GraphDatabase(HOST, PORT, DB_LOCATION)
			g = gd.graph
			user_node = g.node(type='user', username=username)
			if user_node is not None:
				if get_hashed_password(password, user_node.salt) == user_node.password:
					headers = remember(request, username)
					return HTTPFound(location=self.came_from, headers=headers)
			return {
				'username': username,
				'password': password,
				'message': 'Username or password is incorrect',
				}
		return {
			'username': '',
			'password': '',
			'message': '',
			}

	@view_config(route_name='logout')
	def logout(self):
		request = self.request
		headers = forget(request)
		return HTTPFound(location=self.came_from, headers=headers)

	@view_config(route_name='register', renderer='templates/register.pt')
	def register(self):
		request = self.request
		error_message1 = ''
		error_message2 = ''
		error_message3 = ''
		username = ''
		password = ''
		email_address = ''
		if 'form.submitted' in request.params:
			username = request.params['username']
			email_address = request.params['email_address']
			password = request.params['password']
			# open/create the database containing our user nodes
			gd = GraphDatabase(HOST, PORT, DB_LOCATION)
			g = gd.graph
			username_node = g.node(type='user', username=username)
			email_node = g.node(type='user', email_address=email_address)
			error = False
			if len(username) < 3:
				error_message1 = 'Username needs to be 3 or more characters.'
				error = True
			if username_node is not None:
				error_message1 = '\nUsername is already taken'
				error = True
			if not re.match(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:[A-Z]{2}|com|org|net|edu|gov|mil|biz|info|mobi|name|aero|asia|jobs|museum)\b", email_address):
				error_message2 = '\nEmail address is not valid.'
				email_address = ''
				error = True
			if email_node is not None:
				error_message2 = '\nEmail address is already taken.'
				email_address = ''
				error = True
			if len(password) < 3:
				error_message3 = '\nPassword needs to be 3 or more characters.'
				error = True
			if not error:
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
				user = g.add_node(properties=user_properties)
				user.properties['userid'] = user.id
				gd.save()
				# authenticate the newly registered user
				headers = remember(request, username)
				return HTTPFound(location=self.came_from, headers=headers)
		return {
			'error_message1': error_message1,
			'error_message2': error_message2,
			'error_message3': error_message3,
			'username': username,
			'email_address': email_address,
			'password': password,
			}



#class View(BaseMacro):
#	def __init__(self, request):
#		self.request = request
#		self.user_menu_items = user_menu_items(request)
#		self.main_menu_items = main_menu_items(request)
#		self.logged_in = authenticated_userid(request)
#	
#	def get_owned_replays(self):
#		if not self.logged_in:
#			return tuple()
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		user = g.node(username=self.logged_in)
#		owned_replays = g.find_reachable_nodes_from(user, owns='outgoing')
#		return tuple([replay.id for replay in owned_replays])
#	

#	

#			
#	@view_config(route_name='faq')
#	def faq(self):
#		return {}
#	
#	@view_config(route_name='feedback')
#	def feedback(self):
#		return {}
#	

#
#class ReplaysView(View):	
#	@view_config(route_name='replays', renderer='templates/base-replays.pt')
#	def replays(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		replay_nodes = g.nodes(type='replay')
#		return {
#			'replay_list': get_replays(replay_nodes),
#			}
#
#
#
#class UserReplaysView(ReplaysView):
#		
#		@view_config(route_name='your_replays', renderer='templates/base-replays-user.pt')
#	def your_replays(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		
#		user_node = g.node(type='user', username=self.logged_in)
#		if user_node is not None:
#			replay_nodes = user_node.adjacent_nodes(type='replay')
#			return {
#				'replay_list':get_replays(replay_nodes),
#				}
#		else:
#			return HTTPFound(self.request.route_url('replays'))
#	
#	@view_config(route_name='your_reviewed_replays', renderer='templates/base-replays-reviewed')
#	def your_reviewed_replays(self):
#		return {}
#	@view_config(route_name='your_replays', renderer='templates/base-replays-user.pt')
#	def your_replays(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		
#		user_node = g.node(type='user', username=self.logged_in)
#		if user_node is not None:
#			replay_nodes = user_node.adjacent_nodes(type='replay')
#			return {
#				'replay_list':get_replays(replay_nodes),
#				}
#		else:
#			return HTTPFound(self.request.route_url('replays'))
#	
#	@view_config(route_name='your_reviewed_replays', renderer='templates/base-replays-reviewed')
#	def your_reviewed_replays(self):
#		return {}
#	
#	
#	
#	
#class ReplayView(View):
#	def __init__(self, request):
#		super().__init__(request)
#		renderer = get_renderer('templates/replay.pt')
#		replay_macro = renderer.implementation().macros['replay_macro']
#		self.replay_macro = replay_macro
#		
#		self.gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		self.g = self.gd.graph
#		self.replay_id = int(self.request.matchdict['replay_id'])
#		self.replay_node = self.g.node(self.replay_id, type='replay')
#		self.template_dict = self.get_replay_details(self.replay_node)
#	
#	@view_config(route_name='comment_on_replay')
#	def comment_on_replay(self):
#		if 'form' in self.request.params:
#			name = self.request.params['name']
#			comment = self.request.params['comment']
#			comment_node = self.g.add_node(type="comment", name=name, 
#									comment=comment, datetime=datetime.now())
#			self.g.add_edge(self.replay_node, 'owns', comment_node)
#			if self.logged_in:
#				user_node = self.g.node(username=self.logged_in)
#				self.g.add_edge(user_node, 'owns', comment_node)
#			self.gd.save()
#		return HTTPFound(self.request.route_url('replay', 
#											replay_id=self.replay_id))
#	
#	@view_config(route_name='replay', renderer='templates/base-replay.pt')
#	def replay(self):
#		if self.template_dict is None:
#			# HTTP exception/redirect
#			pass
#		comment_nodes = self.replay_node.adjacent_nodes('owns', 
#													'outgoing', 
#													type='comment')
#		comments = []
#		for comment_node in comment_nodes:
#			
#			dt = comment_node.datetime
#			ampm = 'am' if dt.hour < 12 else 'pm'
#			hour = None
#			if dt.hour < 1:
#				hour = '12'
#			elif 1 <= dt.hour < 13:
#				hour = str(dt.hour)
#			elif 13 <= dt.hour < 24:
#				hour = str(dt.hour % 12)
#			else:
#				hour = '12'
#			comments.append({'name': comment_node.name, 
#						'comment': comment_node.comment,
#						'datetime': custom_strftime('%B {S}, %Y '+hour+':%M'+ampm, comment_node.datetime)
#						})
#		self.template_dict['comments'] = tuple(comments)
#		return self.template_dict
#	
#	
#	@view_config(route_name='replay_reviews', renderer='templates/base-replay.pt')
#	def replay_reviews(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		
#		askable_users = [user.username 
#						for user in g.nodes(type='user') 
#						if user.username != self.logged_in]
#		
#		# the replay id of this replay
#		replay_id = int(self.request.matchdict['replay_id'])
#		# get node associated with this id
#		replay_node = g.node(replay_id)
#		# if node is a replay node
#		if replay_node.type != 'replay':
#			# TODO: http exception
#			pass
#		# get replay details template dict
#		template_dict = self.get_replay_details(replay_node)
#		# to see if the user should be able to see the reviews at all
#		template_dict['owned_replay_ids'] = self.get_owned_replays()
#		# get all review nodes owned by this replay
#		review_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type='review')
#		# if there are any review nodes owned by this replay
#		if not review_nodes:
#			# can't ask reviewers to review again
#			template_dict['askable_users'] = askable_users
#			template_dict['reviewers'] = []
#			template_dict['review'] = None
#			return template_dict
#		# the reviewers that wrote the reviews
#		review_owner_nodes = [review_node.adjacent_node(type='user')
#							for review_node in review_nodes]
#		# reviewers and review_ids indices are matched
#		reviewers = [node.username for node in review_owner_nodes]
#		review_ids = [review_node.id for review_node in review_nodes]
#		template_dict['reviewers'] = tuple(zip(reviewers, review_ids))
#		review = dict(review_nodes[0].properties) # should have no nested objs
#		template_dict['review'] = review
#		# determine the users that can be asked for a review
#		template_dict['askable_users'] = self.diff(askable_users, reviewers)
#		
#		return template_dict
#
#
class BehindTheScenes(object):
	def __init__(self, request):
		self.request = request
		self.gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		self.g = self.gd.graph



	@view_config(route_name='upload_replay', request_method='POST')
	def upload_replay(self):
		request = self.request
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
		blue_team = []
		purple_team = []
		for player in replay_data['players']:
			# find out who's pov it is 
			if replay_data['accountID'] == player['accountID']:
				pov = player['summoner']
			# parse the items for the player
			items = []
			for item in ('item1', 'item2', 'item3', 'item4', 'item5', 'item6'):
				if item in player:
					items.append(player[item])
				else:
					items.append(None)

			def getPlayer(attribute):
				"""Returns 0 if attribute doesn't exist"""
				if attribute in player:
					return player[attribute]
				else:
					return 0
			# put all the player data into one dictionary
			champion_name = player['champion'] if player['champion'] != 'MonkeyKing' else 'Wukong'
			player_data = {
						'summoner_name': player['summoner'],
						# league replay hates itself
						'champion_name': champion_name,
						# for champion image off official site
						'champion_id': str(HEROES[champion_name.lower()]),
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
			team.append(player_data)

		# open/create the replay database
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
							'client_version': replay_data['clientVersion'],
							'recorder_version': replay_data['replayVersion'],
							'date_recorded': datetime.fromtimestamp(replay_data['timestamp']),
							'date_uploaded': datetime.now(),
							'blue_team': blue_team,
							'purple_team': purple_team,
							}

		# add a new replay node to the graph return it
		replay = self.g.add_node(properties=replay_properties)

		# put the filename, and location into the replay node
		filename = str(replay.id) + '.lrf'
		location = REPLAY_FOLDER_LOCATION + filename

		replay.filename = filename
		replay.location = location

		# relate this replay node to the user node that uploaded it
		user = self.g.node(username=authenticated_userid(request))
		self.g.add_edge(user, 'owns', replay)

		# write replay file to disk
		replay_file.seek(0)
		with open(location, 'wb') as f:
			data = replay_file.read(2 << 16)
			while data:
				f.write(data)
				data = replay_file.read(2 << 16)

		# save changes made to the database to disk
		self.gd.save()

		return HTTPFound('/replays')

@view_config(route_name='download_replay')
def download_replay(request):
	filename = request.matchdict['id'] + '.' + request.matchdict['ext']
	response = Response(
					content_type='application/force-download',
					content_disposition='attachment; filename=' + filename,
					)
	if os.path.isfile(REPLAY_FOLDER_LOCATION + filename):
		response.app_iter = open(REPLAY_FOLDER_LOCATION + filename, 'rb')
		response.content_length = os.path.getsize(REPLAY_FOLDER_LOCATION + filename)
		return response
	else:
		raise HTTPNotFound

@view_config(route_name='save_owner_comment')
def save_owner_comment(request):
	logged_in = authenticated_userid(request)
	if not logged_in:
		raise HTTPNotFound

	gd = GraphDatabase(HOST, PORT, DB_LOCATION)
	g = gd.graph

	replay_id = int(request.matchdict['replay_id'])
	if 'form' in request.params:
		replay_node = g.node(replay_id, type='replay')
		if replay_node is None:
			raise HTTPNotFound
		owner_comment = request.params['owner_comment']
		if owner_comment == '':
			request.session.flash('Required. Asshole.', 'error_queue')
			return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))
		replay_node.owner_comment = owner_comment
		gd.save()
		request.session.flash('Saved.', 'success_queue')
		return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))
	log.debug('save_owner_comment: not logged in or bad replay_id')
	raise HTTPNotFound

@view_config(route_name='ask_for_review')
def ask_for_review(request):
	logged_in = authenticated_userid(request)
	if not logged_in:
		raise HTTPNotFound

	gd = GraphDatabase(HOST, PORT, DB_LOCATION)
	g = gd.graph
	log.debug(request.params)
	replay_id = int(request.matchdict['replay_id'])
	if 'form' in request.params:
		# the replay to review	
		replay_node = g.node(replay_id, type='replay')
		if replay_node is None:
			raise HTTPNotFound
		# the reviewee's comment to the reviewer
		owner_comment = request.params['owner_comment']
		if owner_comment == '':
			request.session.flash('Required. Asshole.', 'error_queue')
			return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))
		replay_node.owner_comment = owner_comment
		# the user to ask
		if 'username' not in request.params:
			request.session.flash('No one to ask.', 'asked_error')
			return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))
		askee_node = g.node(username=request.params['username'])
		if askee_node is None:
			raise HTTPNotFound
		# connect the askee to the replay
		g.add_edge(askee_node, 'asked_to_review', replay_node)
		gd.save()
		request.session.flash('Asked successfully.', 'asked_successfully')
		# TODO: redirect to the page that shows you asked the person for a review
		return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))
	return HTTPFound(request.route_url('yourreplaystuff-replays-replay_id-reviews', replay_id=replay_id))

