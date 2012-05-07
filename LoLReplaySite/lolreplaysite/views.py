from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPFound, HTTPForbidden, HTTPNotFound, HTTPInternalServerError, HTTPUnauthorized
from pyramid.renderers import get_renderer
from pyramid.security import remember, forget, authenticated_userid

from graphdatabase import GraphDatabase
from lolreplaysite.helpers import *
from lolreplaysite.constants import REPLAY_FOLDER_LOCATION, DB_LOCATION
from lolreplaysite.constants import HOST, PORT, HERO_ID
from lolreplaysite.macros import *



import struct, json, os, hashlib, uuid, re, logging
from datetime import datetime
import copy
from pyramid.exceptions import NotFound

log = logging.getLogger(__name__)





class Base(object):
	def __init__(self, request):
		renderer = get_renderer('templates/macros/base.pt')
		self.base_macro = renderer.implementation().macros['base']
		self.request = request
		self.logged_in_user = authenticated_userid(request)
		route_name = request.matched_route.name
		self.user_menu_items = (
							{
							'label': 'Your Replay Stuff',
							'href': request.route_url('your_replays'),
							'active': route_name == 'your_replays' or route_name == 'your_reviewed_replays',
							},
							{
							'label': 'Your Review Stuff',
							'href': request.route_url('reviews_asked_of_you'),
							'active': route_name == 'reviews_asked_of_you' or route_name == 'reviews_asked_of_others' or route_name == 'reviews_by_you' or route_name == 'reviews_by_others',
							}
							)
		self.main_menu_items = (
							{
							'label': 'Replays',
							'href': request.route_url('replays'),
							'active': route_name == 'replays',
							},
							{
							'label': 'FAQ',
							'href': request.route_url('faq'),
							'active': route_name == 'faq',
							},
							{
							'label': 'Feedback',
							'href': '#',
							'active': False,
							},
							{
							'label': 'Upload',
							'href': request.route_url('upload'),
							'active': route_name == 'upload'
							}
							)
		self.request = request

@view_config(route_name='upload', renderer='templates/upload.pt')
class Upload(Base):
	def __init__(self, request):
		super().__init__(request)
		
	def __call__(self):
		if not self.logged_in_user:
			self.request.session['came_from'] = '/upload'
			return HTTPFound(self.request.route_url('login'))
		return {}

@view_config(route_name='faq', renderer='templates/faq.pt')
class Faq(Base):
	def __init__(self, request):
		super().__init__(request)
	def __call__(self):
		return {}

def get_replays_info(request, _replays):
	replays = []
	for _replay in _replays:
		pov_summoner_name = _replay.pov
		pov_champion_name = None
		pov_champion_href = None
		teams = []
		for _team in (_replay.purple_team, _replay.blue_team):
			team = []
			for _player in _team:
				player_summoner_name = _player['summoner_name']
				player_champion_name = _player['champion_name']
				player_champion_href = CHAMPION_HREF.format(HERO_ID[player_champion_name.lower()])
				if player_summoner_name == pov_summoner_name:
					pov_champion_name = player_summoner_name
					pov_champion_href = player_champion_href
				player = {
						'summoner_name': player_summoner_name,
						'champion_name': player_champion_name,
						'champion_href': player_champion_href,
						}
				team.append(player)
			teams.append(team)
		hours = _replay.length // 3600
		minutes = _replay.length // 60
		seconds = _replay.length % 60
		# replay must have an owner
		owner = _replay.adjacent_node('owns', 'incoming', type='user')
		if not owner:
			log.debug('replays: replay has no owner')
			raise HTTPInternalServerError
		_reviewers = _replay.adjacent_nodes('reviewed', 'incoming', type='user')
		reviewers = [_reviewer.username for _reviewer in _reviewers]
		_users_asked_to_review = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
		users_asked_to_review = [_user.username for _user in _users_asked_to_review]
		replay = {
				'title': _replay.title,
				'date_recorded': _replay.date_recorded.strftime("%a %d-%m-%y"),
				'pov_summoner_name': pov_summoner_name,
				'pov_champion_name': pov_champion_name,
				'pov_champion_href': pov_champion_href,
				'teams': teams,
				'length': "{0}:{1}:{2}".format(hours, minutes, seconds),
				'href': request.route_url('comments', replay_id=_replay.id),
				'download_href': request.route_url('download_replay', replay_id=_replay.id),
				'owner': owner.username,
				'reviewers': reviewers,
				'users_asked_to_review': users_asked_to_review,
				}
		replays.append(replay)
	return replays

@view_config(route_name='replays', renderer='templates/replays.pt')
class Replays(Base):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replays.pt')
		self.replays_macro = renderer.implementation().macros['replays']
		self.request = request
		
	def __call__(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		_replays = g.nodes(type='replay')
		return {'replays': get_replays_info(self.request, _replays)}


class YourReplayStuff(Base):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/your_replay_stuff.pt')
		self.your_replay_stuff_macro = renderer.implementation().macros['your_replay_stuff']
		route_name = request.matched_route.name
		self.stuff_menu_items = (
							{
							'label': 'All Replays',
							'href': request.route_url('your_replays'),
							'active': route_name == 'your_replays'
							},
							{
							'label': 'Reviewed Replays',
							'href': request.route_url('your_reviewed_replays'),
							'active': route_name == 'your_reviewed_replays'
							},
							)


@view_config(route_name='your_replays', renderer='templates/your_replays.pt')
class YourReplays(YourReplayStuff):
	def __init__(self, request):
		log.debug(request.matched_route.name)
		super().__init__(request)
		renderer = get_renderer('templates/macros/replays.pt')
		self.replays_macro = renderer.implementation().macros['replays']
		self.request = request
		
	def __call__(self):
		if not self.logged_in_user:
			log.debug('YourReplays', 'client is not logged in')
			raise HTTPUnauthorized
		
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('owns', 'outgoing', type='replay')
		return {'replays': get_replays_info(self.request, _replays)}

@view_config(route_name='your_reviewed_replays', renderer='templates/your_replays.pt')
class YourReviewedReplays(YourReplayStuff):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replays.pt')
		self.replays_macro = renderer.implementation().macros['replays']
		self.request = request
		
	def __call__(self):
		if not self.logged_in_user:
			log.debug('YourReviewedReplays', 'client is not logged in')
			raise HTTPUnauthorized
		
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('owns', 'outgoing', type='replay')
		__replays = []
		for _replay in _replays:
			if _replay.adjacent_node('reviewed', 'incoming', type='user'):
				__replays.append(_replay)
		return {'replays': get_replays_info(self.request, __replays)}

class YourReviewStuff(Base):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/your_review_stuff.pt')
		self.your_review_stuff_macro = renderer.implementation().macros['your_review_stuff']
		self.request = request
		route_name = request.matched_route.name
		self.stuff_menu_items1 = (
							{
							'label': 'of you',
							'href': request.route_url('reviews_asked_of_you'),
							'active': route_name == 'reviews_asked_of_you'
							},
							{
							'label': 'of others',
							'href': request.route_url('reviews_asked_of_others'),
							'active': route_name == 'reviews_asked_of_others'
							},
							)
		self.stuff_menu_items2 = (
							{
							'label': 'by you',
							'href': request.route_url('reviews_by_you'),
							'active': route_name == 'reviews_by_you'
							},
							{
							'label': 'by others',
							'href': request.route_url('reviews_by_others'),
							'active': route_name == 'reviews_by_others'
							},
							)

@view_config(route_name='reviews_asked_of_you', renderer='templates/reviews_asked_of_you.pt')
class ReviewsAskedOfYou(YourReviewStuff):
	def __init__(self, request):
		super().__init__(request)
	
	def __call__(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		if not self.logged_in_user:
			log.debug('ReviewsAskedOfYou: client not logged in')
			raise HTTPUnauthorized
		
		
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('asked_to_review', 'outgoing', type='replay')
		review_requests = []
		for _replay in _replays:
			asker = _replay.adjacent_node('owns', 'incoming', type='user').username
			review_request = {
					'asker': asker,
					'title': _replay.title,
					'href': self.request.route_url('reviews', replay_id=_replay.id)
					}
			review_requests.append(review_request)
		return {'review_requests': reversed(review_requests),}

@view_config(route_name='reviews_asked_of_others', renderer='templates/reviews_asked_of_others.pt')
class ReviewsAskedOfOthers(YourReviewStuff):
	def __init__(self, request):
		super().__init__(request)
	
	def __call__(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		if not self.logged_in_user:
			log.debug('ReviewsAskedOfOthers: client not logged in')
			raise HTTPUnauthorized
		
		
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('owns', 'outgoing', type='replay')
		
		review_requests = []
		for _replay in _replays:
			_users_asked_to_review = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
			for __user in _users_asked_to_review:
				review_request = {
						'askee': __user.username,
						'title': _replay.title,
						'href': self.request.route_url('reviews', replay_id=_replay.id)
						}
				review_requests.append(review_request)
		return {'review_requests': reversed(review_requests),}
	
@view_config(route_name='reviews_by_you', renderer='templates/reviews_by_you.pt')
class ReviewsByYou(YourReviewStuff):
	def __init__(self, request):
		super().__init__(request)
	
	def __call__(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		if not self.logged_in_user:
			log.debug('ReviewsAskedOfOthers: client not logged in')
			raise HTTPUnauthorized
		
		
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('reviewed', 'outgoing', type='replay')
		review_requests = []
		for _replay in _replays:
			_owner = _replay.adjacent_node('owns', 'incoming', type='user')
			review_request = {
					'owner': _owner.username,
					'title': _replay.title,
					'href': self.request.route_url('reviews', replay_id=_replay.id)
					}
			review_requests.append(review_request)
		return {'review_requests': reversed(review_requests),}

@view_config(route_name='reviews_by_others', renderer='templates/reviews_by_others.pt')
class ReviewsByOthers(YourReviewStuff):
	def __init__(self, request):
		super().__init__(request)
	
	def __call__(self):
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		if not self.logged_in_user:
			log.debug('ReviewsAskedOfOthers: client not logged in')
			raise HTTPUnauthorized
		
		_user = g.node(username=self.logged_in_user, type='user')
		_replays = _user.adjacent_nodes('owns', 'outgoing', type='replay')
		review_requests = []
		for _replay in _replays:
			_reviewers = _replay.adjacent_nodes('reviewed', 'incoming', type='user')
			for _reviewer in _reviewers:
				review_request = {
						'reviewer': _reviewer.username,
						'title': _replay.title,
						'href': self.request.route_url('reviews', replay_id=_replay.id)
						}
				review_requests.append(review_request)
		return {'review_requests': reversed(review_requests),}

class Replay(Base):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/replay.pt')
		self.replay_macro = renderer.implementation().macros['replay']
		
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		
		g = gd.graph
		self.replay_id = int(request.matchdict['replay_id'])
		_replay = g.node(self.replay_id, type='replay')
		if _replay is None:
			log.debug('replay: client sent us bad replay_id')
			raise HTTPNotFound
		
		
		pov_summoner_name = _replay.pov
		pov_champion_name = None
		pov_champion_href = None
		teams = []
		for _team in (_replay.purple_team, _replay.blue_team):
			team = []
			for _player in _team:
				 player_summoner_name = _player['summoner_name']
				 player_champion_name = _player['champion_name']
				 player_champion_href = CHAMPION_HREF.format(HERO_ID[player_champion_name.lower()])
				 if player_summoner_name == pov_summoner_name:
				 	pov_champion_name = player_summoner_name
				 	pov_champion_href = player_champion_href
				 item_hrefs = []
				 for item_id in _player['items']:
				 	if item_id is None:
				 		item_hrefs.append(item_id)
				 	else:
				 		item_hrefs.append(ITEM_HREF.format(item_id))
				 player = {
						'summoner_name': player_summoner_name,
						'champion_name': player_champion_name,
						'champion_href': player_champion_href,
						'level': _player['level'],
						'kills': _player['kills'],
						'deaths': _player['deaths'],
						'assists': _player['assists'],
						'minions': _player['lane_minions_killed'] + _player['neutral_minions_killed'],
						'gold': _player['gold'],
						'summoner_spell_hrefs': [SUMMONER_SPELL_HREF.format(spell_id) for spell_id in _player['summoner_spells']],
						'item_hrefs': item_hrefs,
						}
				 team.append(player)
			teams.append(team)
		hours = _replay.length // 3600
		minutes = _replay.length // 60
		seconds = _replay.length % 60
		# replay must have an owner or validation/upload failed
		owner = _replay.adjacent_node('owns', 'incoming', type='user')
		if not owner:
			log.debug('replay: replay has no owner')
			raise HTTPInternalServerError
		_reviewers = _replay.adjacent_nodes('reviewed', 'incoming', type='user')
		reviewers = [_reviewer.username for _reviewer in _reviewers]
		_users_asked_to_review = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
		users_asked_to_review = [_user.username for _user in _users_asked_to_review]
		self.replay = {
				'title': _replay.title,
				'client_version': _replay.client_version,
				'recorder_version': _replay.recorder_version,
				'description': _replay.description,
				'pov_summoner_name': pov_summoner_name,
				'pov_champion_name': pov_champion_name,
				'pov_champion_href': pov_champion_href,
				'date_recorded': _replay.date_recorded.strftime("%a %d-%m-%y"),
				'teams': teams,
				'length': "{0}:{1}:{2}".format(hours, minutes, seconds),
				'download_href': '#', # request.route_url('download', replay_id=_replay.id)
				'owner': owner.username,
				'reviewers': reviewers,
				'users_asked_to_review': users_asked_to_review,
				'reviews_href': request.route_url('reviews', replay_id=self.replay_id),
				'comments_href': request.route_url('comments', replay_id=self.replay_id)
				}
		
	def __call__(self):
		return self.replay

@view_config(route_name='comments', renderer='templates/comments.pt')
class Comments(Replay):
	# TODO: restrict author name length, and text length
	# TODO: think about text formatting options
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/comments.pt')
		self.comments_macro = renderer.implementation().macros['comments']
		
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		_replay = g.node(self.replay_id, type='replay')
		_comments = _replay.adjacent_nodes('owns', 'outgoing', type='comment')
		comments = []
		for _comment in _comments:
			dt = _comment.datetime
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
			comment = {
					'author': _comment.author,
					'text': _comment.text,
					'date_posted': custom_strftime('%B {S}, %Y ' + hour + ':%M' + ampm, dt),
					'last_edited': None,
					'is_user': _comment.adjacent_node('owns', 'incoming' , type='user') is not None,
					}
			comments.append(comment)
		self.template_variables = {
							'default_name': 'Artificial Owl',
							'post_comment_href': request.route_url('post_comment', replay_id=self.replay_id),
							'comments': comments,
							'no_comments_text': 'No one has left a comment, yet.'
							}
		
	def __call__(self):
		self.template_variables.update(self.replay)
		return self.template_variables

@view_config(route_name='post_comment')
class PostComment(object):
	def __init__(self, request):
		self.request = request
	
	def __call__(self):
		request = self.request
		replay_id = int(request.matchdict['replay_id'])
		if 'form' in request.params:
			gd = GraphDatabase(HOST, PORT, DB_LOCATION)
			g = gd.graph
			# validate inputs
			_replay = g.node(replay_id, type='replay')
			if _replay is None:
				log.debug('PostComment: replay_id given does not exist')
				raise HTTPNotFound
			author = request.params['author']
			if author == '':
				author = 'Artificial Owl'
			text = request.params['text']
			if text == '':
				request.session.flash("You're in a desert, walking along in the sand, when all of a sudden you look down...", 'comment_error')
				return HTTPFound(request.route_url('comments', replay_id=replay_id))
			# input into database
			_comment = g.add_node(type="comment", author=author, text=text, datetime=datetime.now(), last_edited=None)
			g.add_edge(_replay, 'owns', _comment)
			logged_in_user = authenticated_userid(request)
			if logged_in_user:
				_user = g.node(username=logged_in_user, type='user')
				g.add_edge(_user, 'owns', _comment)
			gd.save()
		return HTTPFound(request.route_url('comments', replay_id=replay_id))

@view_config(route_name="reviews", renderer='templates/reviews.pt')
class Reviews(Replay):
	def __init__(self, request):
		super().__init__(request)
		renderer = get_renderer('templates/macros/reviews.pt')
		self.reviews_macro = renderer.implementation().macros['reviews']
		self.request
		
	def __call__(self):
		request = self.request
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		# note below can be done without this cause we have
		# reviewers/asked_users/owner from Replay but what the hell anyway
		_replay = g.node(self.replay_id, type='replay')
		if _replay is None:
			log.debug('Reviews: replay_id given does not exist')
			raise HTTPNotFound
		
		# get reviewers
		_reviewers = _replay.adjacent_nodes('reviewed', 'incoming', type='user')
		reviewers = [_reviewer.username for _reviewer in _reviewers]
		
		# get users asked to review this replay
		_users_asked_to_review = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
		users_asked_to_review = [_user.username for _user in _users_asked_to_review]
		
		# get users eligible to review this replay
		_users = g.nodes(type='user')
		all_users = [_user.username for _user in _users if _user.username != self.logged_in_user] # except logged in user
		users_eligible_to_review = diff(diff(all_users, reviewers), users_asked_to_review)
		
		# get reviewee comment if there is one
		reviewee_comment = None
		if 'reviewee_comment' in _replay.properties:
			reviewee_comment = _replay.reviewee_comment
		
		review_text = ''
		
		index = 0
		current_reviewer = None
		if reviewers:
			current_reviewer = reviewers[index]
		if 'form' in request.params:
			current_reviewer = request.params['reviewer']
			index = reviewers.index(current_reviewer)
		else:
			if self.logged_in_user in reviewers:
				index = reviewers.index(self.logged_in_user)
				
		
		if reviewers:
			_reviewer = _reviewers[index]
			_reviews = _reviewer.adjacent_nodes('owns', 'outgoing', type='review')
			for _review in _reviews:
				__replay = _review.adjacent_node('owns', 'incoming', type='replay')
				if __replay.id == _replay.id:
					review_text = _review.text
					break
		
		self.replay.update({
						'display_review_href': request.route_url('reviews', replay_id=self.replay_id),
			'ask_user_for_review_href': request.route_url('ask_for_review', replay_id=self.replay_id),
			'save_reviewee_comment_href': request.route_url('save_reviewee_comment', replay_id=self.replay_id),
			'save_reviewer_comment_href': request.route_url('save_reviewer_comment', replay_id=self.replay_id),
			'reviewee_comment': reviewee_comment,
			'users_eligible_to_review': users_eligible_to_review,
			'reviewers': reviewers,
			'no_reviews_text': 'This replay has not been reviewed yet.',
			'review_text': review_text,
			'current_reviewer': current_reviewer,
			})
		return self.replay 


@view_config(route_name='ask_for_review')
class AskForReview(object):
	def __init__(self, request):
		self.request = request
	
	def __call__(self):
		request = self.request
		logged_in = authenticated_userid(request)
		if not logged_in:
			raise HTTPNotFound
	
		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
		g = gd.graph
		
		replay_id = int(request.matchdict['replay_id'])
		if 'form' in request.params:
			log.debug(request.params)
			# the replay to review	
			_replay = g.node(replay_id, type='replay')
			if _replay is None:
				log.debug("AskForReview: replay_id doesn't exist")
				raise HTTPNotFound
			# the reviewee's comment to the reviewer
			reviewee_comment = request.params['reviewee_comment']
			if reviewee_comment == '':
				request.session.flash("Required.", 'error_queue')
				return HTTPFound(request.route_url('reviews', replay_id=replay_id))
			_replay.reviewee_comment = reviewee_comment
			# the user to ask
			if 'username' not in request.params:
				request.session.flash('The tortoise lays on its back...', 'asked_error')
				return HTTPFound(request.route_url('reviews', replay_id=replay_id))
			askee_node = g.node(username=request.params['username'])
			if askee_node is None:
				log.debug("AskForReview: user being asked doesn't exist")
				raise HTTPNotFound
			# connect the askee to the replay
			g.add_edge(askee_node, 'asked_to_review', _replay)
			gd.save()
			request.session.flash('Asked successfully.', 'asked_successfully')
			# TODO: redirect to the page that shows you asked the person for a review
		return HTTPFound(request.route_url('reviews', replay_id=replay_id))

@view_config(route_name='save_reviewee_comment')
def save_reviewee_comment(request):
	logged_in = authenticated_userid(request)
	if not logged_in:
		log.debug('save_reviewee_comment: not logged in')
		raise HTTPNotFound

	gd = GraphDatabase(HOST, PORT, DB_LOCATION)
	g = gd.graph

	replay_id = int(request.matchdict['replay_id'])
	if 'form' in request.params:
		replay_node = g.node(replay_id, type='replay')
		if replay_node is None:
			log.debug("save_reviewee_comment: replay_id doesn't exist")
			raise HTTPNotFound
		reviewee_comment = request.params['reviewee_comment']
		if reviewee_comment == '':
			request.session.flash('*Required', 'error_queue')
			return HTTPFound(request.route_url('reviews', replay_id=replay_id))
		replay_node.reviewee_comment = reviewee_comment
		gd.save()
		request.session.flash('Saved.', 'success_queue')
		return HTTPFound(request.route_url('reviews', replay_id=replay_id))
	log.debug('save_owner_comment: not logged in or bad replay_id')
	raise HTTPNotFound

@view_config(route_name='save_reviewer_comment')
def save_reviewer_comment(request):
	logged_in_user = authenticated_userid(request)
	gd = GraphDatabase(HOST, PORT, DB_LOCATION)
	g = gd.graph
	replay_id = int(request.matchdict['replay_id'])
	_replay = g.node(replay_id, type='replay')
	if _replay is None:
		log.debug("save_reviewer_comment: replay_id doesn't exist")
		raise HTTPNotFound
	# get reviewers
	_users_asked_to_review = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
	users_asked_to_review = [_user.username for _user in _users_asked_to_review]
	
	_reviewers = _replay.adjacent_nodes('reviewed', 'incoming', type='user')
	reviewers = [_reviewer.username for _reviewer in _reviewers]
	
	if not logged_in_user:
		log.debug('save_reviewer_comment: not logged on')
		raise HTTPNotFound
	
	if logged_in_user not in users_asked_to_review and logged_in_user not in reviewers:
		log.debug('save_reviewer_comme: logged in user is not reviewer')
		raise HTTPUnauthorized
	
	if 'form' in request.params:
		# didn't validate review_text cause client not sending it dont matter
		# server can error all it likes in that case
		review_text = request.params['review_text']
		if review_text == '':
			request.session.flash('Required.', 'review_error')
			return HTTPFound(request.route_url('reviews', replay_id=replay_id))
		_user = g.node(username=logged_in_user, type='user')
		if logged_in_user in users_asked_to_review:
			review_properties = {
				'type': 'review',
				'author': logged_in_user,
				'text': review_text,
				'datetime': datetime.now(),
				'last_edited': None,
				}
			_review = g.add_node(properties=review_properties)
			
			if _user is None:
				log.debug("save_reviewer_comment: logged in user doesn't exist")
				raise HTTPNotFound
			
			g.add_edge(_user, 'owns', _review)
			g.add_edge(_replay, 'owns', _review)
			_edges = _user.edges('asked_to_review', 'outgoing')
			for _edge in _edges:
				if (_edge.end_node.id == replay_id):
					g.remove_edge(_edge.id)
					break
			g.add_edge(_user, 'reviewed', _replay)
		else:
			_reviews = _user.adjacent_nodes('owns', 'outgoing', type='review')
			for _review in _reviews:
				__replay = _review.adjacent_node('owns', 'incoming', type='replay')
				if __replay.id == _replay.id:
					_review.text = review_text
					break
		gd.save()
		request.session.flash('Saved.', 'review_success')
	return HTTPFound(request.route_url('reviews', replay_id=replay_id))

#class BaseView(object):
#	def __init__(self, request):
#		renderer = get_renderer('templates/macros/base.pt')
#		self.base_macro = renderer.implementation().macros['base_macro']
#		request.session['came_from'] = request.current_route_url()
#		self.request = request
#		self.logged_in = authenticated_userid(request)
#		# TODO: replace these URLs with request.route_url()
#		self.user_menu_items = (
#							{
#							'label': 'Your Replay Stuff',
#							'href': request.route_url('your_replays'),
#							},
#							{
#							'label': 'Your Review Stuff',
#							'href': request.route_url('yourreviewstuff-reviewsaskedofyou'),
#							}
#							)
#		self.main_menu_items = (
#							{
#							'label': 'Replays',
#							'href': request.route_url('replays'),
#							},
#							{
#							'label': 'FAQ',
#							'href': '#',
#							},
#							{
#							'label': 'Feedback',
#							'href': '#',
#							},
#							{
#							'label': 'Upload',
#							'href': request.route_url('upload'),
#							}
#							)
#
#	
#	@view_config(route_name='test', renderer='templates/test.pt')
#	def test(self):
#		return {}
#

#
#
#class ReplaysView(Base):
#	def __init__(self, request):
#		super().__init__(request)
#		renderer = get_renderer('templates/macros/replays_macro.pt')
#		self.replays_macro = renderer.implementation().macros['replays_macro']
#
#	def get_replays(self, replay_nodes):
#		replays = []
#		for _replay in replay_nodes:
#			pov_summoner_name = _replay.pov
#			replay = {
#					'title': _replay.title,
#					'date_recorded': _replay.date_recorded.strftime("%a %d-%m-%y"),
#					'pov_summoner_name': pov_summoner_name,
#					'length': "{0}:{1}:{2}".format(_replay.length // 3600,
#												_replay.length // 60,
#												_replay.length % 60),
#					'id': _replay.id,
#					'filename': _replay.filename,
#					'teams': [],
#					'num_comments': len(_replay.adjacent_nodes('owns', 'outgoing', type='comment')),
#					'num_reviews': len(_replay.adjacent_nodes('owns', 'outgoing', type='review')),
#					}
#			for team in (_replay.blue_team, _replay.purple_team):
#				t = []
#				for player in team:
#					player_summoner_name = player['summoner_name']
#					player_champion_name = player['champion_name']
#					player_champion_id = str(HEROES[player_champion_name.lower()])
#					if player_summoner_name == pov_summoner_name:
#						replay['pov_champion_name'] = player_champion_name
#						replay['pov_champion_id'] = player_champion_id
#					player_data = {
#								'summoner_name': player_summoner_name,
#								'champion_name': player_champion_name,
#								'champion_id': player_champion_id,
#								}
#					t.append(player_data)
#				replay['teams'].append(t)
#			replays.append(replay)
#		return replays
#
#	@view_config(route_name='replays', renderer='templates/replays.pt')
#	def replays(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		replay_nodes = g.nodes(type='replay')
#		return {'replays': self.get_replays(replay_nodes)}
#
#	@view_config(route_name='your_replays', renderer='templates/your_replays.pt')
#	def your_replays(self):
#		if not self.logged_in:
#			return HTTPFound(self.request.route_url('replays'))
#
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		user_node = g.node(type='user', username=self.logged_in)
#		
#		replay_nodes = user_node.adjacent_nodes('owns', 'outgoing', type='replay')
#		return {'replays': self.get_replays(replay_nodes), }
#
#class ReplayView(Base):
#	def __init__(self, request):
#		super().__init__(request)
#		renderer = get_renderer('templates/macros/replay_macro.pt')
#		self.replay_macro = renderer.implementation().macros['replay_macro']
#
#	def get_replay_details(self, _replay):
#		replay = _replay
#		if replay is not None:
#			l = replay.length
#			return {
#				'replay_id': replay.id,
#				'length': "{0}:{1}:{2}".format(l // 3600, l // 60, l % 60),
#				'client_version': replay.client_version,
#				'recorder_version': replay.recorder_version,
#				'pov': replay.pov,
#				'description': replay.description,
#				'title': replay.title,
#				'teams': (copy.deepcopy(replay.blue_team), copy.deepcopy(replay.purple_team)),
#				}
#
#	def get_comments(self, _replay):
#		comment_nodes = _replay.adjacent_nodes('owns',
#													'outgoing',
#													type='comment')
#		comments = []
#		for comment_node in comment_nodes:
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
#						'datetime': custom_strftime('%B {S}, %Y ' + hour + ':%M' + ampm, comment_node.datetime)
#						})
#		return comments
#
#	def get_reviews(self, _replay):
#		review_nodes = _replay.adjacent_nodes('owns', 'outgoing', type='review')
#		return tuple(review_nodes)
#
#	def diff(self, l1, l2):
#		c1 = Counter(l1)
#		c2 = Counter(l2)
#		d = c1 - c2
#		return tuple(d.elements())
#
#	@view_config(route_name='replay', renderer='templates/replay.pt')
#	def replay(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		replay_id = int(self.request.matchdict['replay_id'])
#		_replay = g.node(replay_id, type='replay')
#		if _replay is None:
#			return HTTPFound(self.request.route_url('replays'))
#		template_dict = self.get_replay_details(_replay)
#		template_dict['comments'] = self.get_comments(_replay)
#		return template_dict
#
#	@view_config(route_name='comment_on_replay')
#	def comment_on_replay(self):
#		return {}
#
#class YourReplayStuffReplaysReplay_id(Base):
#	route_name = 'yourreplaystuff-replays-replay_id-{}'
#	template_name = 'templates/{}.pt'.format(route_name)
#
#	def __init__(self, request):
#		super().__init__(request)
#		renderer = get_renderer('templates/macros/replay_macro.pt')
#		self.replay_macro = renderer.implementation().macros['replay_macro']
#		renderer = get_renderer('templates/macros/comments.pt')
#		self.comments_macro = renderer.implementation().macros['comments']
#
#		self.gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		self.g = self.gd.graph
#
#	def get_replay_info(self, _replay):
#		replay = _replay
#		if replay is not None:
#			l = replay.length
#			return {
#				'replay_id': replay.id,
#				'length': "{0}:{1}:{2}".format(l // 3600, l // 60, l % 60),
#				'client_version': replay.client_version,
#				'recorder_version': replay.recorder_version,
#				'pov': replay.pov,
#				'description': replay.description,
#				'title': replay.title,
#				'teams': (copy.deepcopy(replay.blue_team), copy.deepcopy(replay.purple_team)),
#				}
#
#	def get_replay_comments(self, _replay):
#		comment_nodes = _replay.adjacent_nodes('owns', 'outgoing', type='comment')
#		comments = []
#		for comment_node in comment_nodes:
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
#						'datetime': custom_strftime('%B {S}, %Y ' + hour + ':%M' + ampm, comment_node.datetime)
#						})
#		return comments
#
#	def get_replay_reviews(self, _replay):
#		review_nodes = _replay.adjacent_nodes('owns', 'outgoing', type='review')
#		return tuple(review_nodes)
#
#	def get_reviewers(self, _replay):
#		# get all usernames except current user
#		all_usernames = []
#		user_nodes = self.g.nodes(type='user')
#		for user_node in user_nodes:
#			if user_node.username != self.logged_in:
#				all_usernames.append(user_node.username)
#
#		# get usernames of users that have reviewed this replay
#		review_nodes = _replay.adjacent_nodes('owns', 'outgoing', type="review")
#		reviewer_usernames = []
#		for review_node in review_nodes:
#			reviewer_node = review_node.adjacent_node('owns', 'incoming', type='user')
#			reviewer_usernames.append(reviewer_node.username)
#		
#		# get usernames of users that have already been asked to review
#		askees = _replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
#		askee_usernames = []
#		for askee in askees:
#			askee_usernames.append(askee.username)
#		
#		users_minus_reviewer_names = self.diff(all_usernames, reviewer_usernames)
#		eligible_reviewers = self.diff(users_minus_reviewer_names, askee_usernames)
#		
#		# return reviewers and eligible reviewers usernames
#		return reviewer_usernames, eligible_reviewers
#
#	def diff(self, l1, l2):
#		c1 = Counter(l1)
#		c2 = Counter(l2)
#		d = c1 - c2
#		return tuple(d.elements())
#
#	@view_config(route_name=route_name.format('comments'),
#				renderer=template_name.format('comments'))
#	def comments(self):
#		replay_id = int(self.request.matchdict['replay_id'])
#		_replay = self.g.node(replay_id, type='replay')
#		if _replay is None:
#			raise HTTPNotFound
#
#		template_variables = self.get_replay_info(_replay)
#		template_variables['comments'] = self.get_replay_comments(_replay)
#		template_variables['num_reviews'] = len(self.get_replay_reviews(_replay))
#
#		return template_variables
#
#	@view_config(route_name=route_name.format('reviews'),
#				renderer=template_name.format('reviews'))
#	def reviews(self):
#		replay_id = int(self.request.matchdict['replay_id'])
#		_replay = self.g.node(replay_id, type='replay')
#		if _replay is None:
#			raise HTTPNotFound
#
#		template_variables = self.get_replay_info(_replay)
#		if 'reviewee_comment' in  _replay.properties:
#			template_variables['reviewee_comment'] = _replay.reviewee_comment
#		else:
#			template_variables['reviewee_comment'] = None
#		template_variables['comments'] = self.get_replay_comments(_replay)
#		template_variables['reviews'] = self.get_replay_reviews(_replay)
#		template_variables['num_reviews'] = len(template_variables['reviews'])
#		template_variables['not_reviewed_msg'] = 'This replay has not been reviewed yet.'
#		reviewer_usernames, askable_usernames = self.get_reviewers(_replay)
#		template_variables['askable_usernames'] = askable_usernames
#		template_variables['reviewer_usernames'] = reviewer_usernames
#
#		return template_variables
#
#class YourReviewStuff(Base):
#	def __init__(self, request):
#		super().__init__(request)
#		renderer = get_renderer('templates/macros/your-review-stuff.pt')
#		self.your_review_stuff_macro = renderer.implementation().macros['your-review-stuff']
#
#	@view_config(route_name='yourreviewstuff-reviewsaskedofyou',
#				renderer='templates/yourreviewstuff-reviewsaskedofyou.pt')
#	def reviews_asked_of_you(self):
#		# Gets asker names and the info of the respective replays they want you
#		# to review puts them into a tuple pairs and sends that to the template
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#
#		if not self.logged_in:
#			log.debug('your-review-stuff/reviews-asked-of-you: user is not logged in')
#			raise HTTPNotFound
#
#		user = g.node(type='user', username=self.logged_in)
#		if user is None:
#			log.debug('your-review-stuff/reviews-asked-of-you: username does not exist')
#			raise HTTPNotFound
#		replays = user.adjacent_nodes('asked_to_review', 'outgoing', type='replay')
#		askers_info = []
#		replays_info = []
#		for replay in replays:
#			replay_info = {
#						'id': replay.id,
#						'title': replay.title,
#						}
#			replays_info.append(replay_info)
#			asker = replay.adjacent_node('owns', 'incoming', type='user')
#			if asker is None:
#				log.debug('your-review-stuff/reviews-asked-of-you: asker does not exist')
#				raise HTTPNotFound
#			asker_info = {'username': asker.username}
#			askers_info.append(asker_info)
#
#		return {
#			'askers_and_replays': tuple(zip(askers_info, replays_info))
#			}
#	
#	@view_config(route_name='yourreviewstuff-reviewsaskedofothers',
#				renderer='templates/yourreviewstuff-reviewsaskedofothers.pt')
#	def reviews_asked_of_others(self):
#		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
#		g = gd.graph
#		
#		if not self.logged_in:
#			log.debug('your-review-stuff/reviews-asked-of-others: user is not logged in')
#			raise HTTPNotFound
#		user = g.node(type='user', username=self.logged_in)
#		if user is None:
#			log.debug('your-review-stuff/reviews-asked-of-others: username does not exist')
#			raise HTTPNotFound
#		replays = user.adjacent_nodes('owns', 'outgoing', type='replay')
#		askee_infos = []
#		replay_infos = []
#		for replay in replays:
#			askees = replay.adjacent_nodes('asked_to_review', 'incoming', type='user')
#			for askee in askees:
#				askee_info = {'username': askee.username}
#				replay_info = {'id': replay.id,
#							'title': replay.title}
#				askee_infos.append(askee_info)
#				replay_infos.append(replay_info)
#		return {'askers_and_replays': tuple(zip(askee_infos, replay_infos))}
#		
class LoginView(object):
	def __init__(self, request):
		self.request = request
		self.came_from = request.route_url('replays')
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
		

#
#
#
##class View(BaseMacro):
##	def __init__(self, request):
##		self.request = request
##		self.user_menu_items = user_menu_items(request)
##		self.main_menu_items = main_menu_items(request)
##		self.logged_in = authenticated_userid(request)
##	
##	def get_owned_replays(self):
##		if not self.logged_in:
##			return tuple()
##		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		g = gd.graph
##		user = g.node(username=self.logged_in)
##		owned_replays = g.find_reachable_nodes_from(user, owns='outgoing')
##		return tuple([replay.id for replay in owned_replays])
##	
#
##	
#
##			
##	@view_config(route_name='faq')
##	def faq(self):
##		return {}
##	
##	@view_config(route_name='feedback')
##	def feedback(self):
##		return {}
##	
#
##
##class ReplaysView(View):	
##	@view_config(route_name='replays', renderer='templates/base-replays.pt')
##	def replays(self):
##		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		g = gd.graph
##		replay_nodes = g.nodes(type='replay')
##		return {
##			'replay_list': get_replays(replay_nodes),
##			}
##
##
##
##class UserReplaysView(ReplaysView):
##		
##		@view_config(route_name='your_replays', renderer='templates/base-replays-user.pt')
##	def your_replays(self):
##		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		g = gd.graph
##		
##		user_node = g.node(type='user', username=self.logged_in)
##		if user_node is not None:
##			replay_nodes = user_node.adjacent_nodes(type='replay')
##			return {
##				'replay_list':get_replays(replay_nodes),
##				}
##		else:
##			return HTTPFound(self.request.route_url('replays'))
##	
##	@view_config(route_name='your_reviewed_replays', renderer='templates/base-replays-reviewed')
##	def your_reviewed_replays(self):
##		return {}
##	@view_config(route_name='your_replays', renderer='templates/base-replays-user.pt')
##	def your_replays(self):
##		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		g = gd.graph
##		
##		user_node = g.node(type='user', username=self.logged_in)
##		if user_node is not None:
##			replay_nodes = user_node.adjacent_nodes(type='replay')
##			return {
##				'replay_list':get_replays(replay_nodes),
##				}
##		else:
##			return HTTPFound(self.request.route_url('replays'))
##	
##	@view_config(route_name='your_reviewed_replays', renderer='templates/base-replays-reviewed')
##	def your_reviewed_replays(self):
##		return {}
##	
##	
##	
##	
##class ReplayView(View):
##	def __init__(self, request):
##		super().__init__(request)
##		renderer = get_renderer('templates/replay.pt')
##		replay_macro = renderer.implementation().macros['replay_macro']
##		self.replay_macro = replay_macro
##		
##		self.gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		self.g = self.gd.graph
##		self.replay_id = int(self.request.matchdict['replay_id'])
##		self.replay_node = self.g.node(self.replay_id, type='replay')
##		self.template_dict = self.get_replay_details(self.replay_node)
##	
##	@view_config(route_name='comment_on_replay')
##	def comment_on_replay(self):
##		if 'form' in self.request.params:
##			name = self.request.params['name']
##			comment = self.request.params['comment']
##			comment_node = self.g.add_node(type="comment", name=name, 
##									comment=comment, datetime=datetime.now())
##			self.g.add_edge(self.replay_node, 'owns', comment_node)
##			if self.logged_in:
##				user_node = self.g.node(username=self.logged_in)
##				self.g.add_edge(user_node, 'owns', comment_node)
##			self.gd.save()
##		return HTTPFound(self.request.route_url('replay', 
##											replay_id=self.replay_id))
##	
##	@view_config(route_name='replay', renderer='templates/base-replay.pt')
##	def replay(self):
##		if self.template_dict is None:
##			# HTTP exception/redirect
##			pass
##		comment_nodes = self.replay_node.adjacent_nodes('owns', 
##													'outgoing', 
##													type='comment')
##		comments = []
##		for comment_node in comment_nodes:
##			
##			dt = comment_node.datetime
##			ampm = 'am' if dt.hour < 12 else 'pm'
##			hour = None
##			if dt.hour < 1:
##				hour = '12'
##			elif 1 <= dt.hour < 13:
##				hour = str(dt.hour)
##			elif 13 <= dt.hour < 24:
##				hour = str(dt.hour % 12)
##			else:
##				hour = '12'
##			comments.append({'name': comment_node.name, 
##						'comment': comment_node.comment,
##						'datetime': custom_strftime('%B {S}, %Y '+hour+':%M'+ampm, comment_node.datetime)
##						})
##		self.template_dict['comments'] = tuple(comments)
##		return self.template_dict
##	
##	
##	@view_config(route_name='replay_reviews', renderer='templates/base-replay.pt')
##	def replay_reviews(self):
##		gd = GraphDatabase(HOST, PORT, DB_LOCATION)
##		g = gd.graph
##		
##		askable_users = [user.username 
##						for user in g.nodes(type='user') 
##						if user.username != self.logged_in]
##		
##		# the replay id of this replay
##		replay_id = int(self.request.matchdict['replay_id'])
##		# get node associated with this id
##		replay_node = g.node(replay_id)
##		# if node is a replay node
##		if replay_node.type != 'replay':
##			# TODO: http exception
##			pass
##		# get replay details template dict
##		template_dict = self.get_replay_details(replay_node)
##		# to see if the user should be able to see the reviews at all
##		template_dict['owned_replay_ids'] = self.get_owned_replays()
##		# get all review nodes owned by this replay
##		review_nodes = replay_node.adjacent_nodes('owns', 'outgoing', type='review')
##		# if there are any review nodes owned by this replay
##		if not review_nodes:
##			# can't ask reviewers to review again
##			template_dict['askable_users'] = askable_users
##			template_dict['reviewers'] = []
##			template_dict['review'] = None
##			return template_dict
##		# the reviewers that wrote the reviews
##		review_owner_nodes = [review_node.adjacent_node(type='user')
##							for review_node in review_nodes]
##		# reviewers and review_ids indices are matched
##		reviewers = [node.username for node in review_owner_nodes]
##		review_ids = [review_node.id for review_node in review_nodes]
##		template_dict['reviewers'] = tuple(zip(reviewers, review_ids))
##		review = dict(review_nodes[0].properties) # should have no nested objs
##		template_dict['review'] = review
##		# determine the users that can be asked for a review
##		template_dict['askable_users'] = self.diff(askable_users, reviewers)
##		
##		return template_dict
##
##
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
			summoner_spells = []
			if 'spell1' in player:
				summoner_spells.append(player['spell1'])
			if 'spell2' in player:
				summoner_spells.append(player['spell2'])
			player_data = {
						'summoner_name': player['summoner'],
						# league replay hates itself
						'champion_name': champion_name,
						# for champion image off official site
						'champion_id': str(HERO_ID[champion_name.lower()]),
						'level': player['level'],
						'kills': getPlayer('kills'),
						'deaths': getPlayer('deaths'),
						'assists': getPlayer('assists'),
						'items': tuple(items),
						'summoner_spells': summoner_spells,
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
	# url_dispatch sanitizes replay id so it has no slashes in it
	# if they put in dots, isfile will stop anything
	filename = request.matchdict['replay_id'] + '.lrf'
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






