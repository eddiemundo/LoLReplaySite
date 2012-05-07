from pyramid.config import Configurator
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.session import UnencryptedCookieSessionFactoryConfig
my_session_factory = UnencryptedCookieSessionFactoryConfig('sekrit2')

from lolreplaysite.security import groupfinder

from pyramid.httpexceptions import default_exceptionresponse_view, HTTPFound
from pyramid.interfaces import IRoutesMapper

class RemoveSlashNotFoundViewFactory(object):
    """Chris McDonough's code. I got it from stackoverflow"""
    def __init__(self, notfound_view=None):
        if notfound_view is None:
            notfound_view = default_exceptionresponse_view
        self.notfound_view = notfound_view

    def __call__(self, context, request):
        if not isinstance(context, Exception):
            # backwards compat for an append_notslash_view registered via
            # config.set_notfound_view instead of as a proper exception view
            context = getattr(request, 'exception', None) or context
        path = request.path
        registry = request.registry
        mapper = registry.queryUtility(IRoutesMapper)
        if mapper is not None and path.endswith('/'):
            noslash_path = path.rstrip('/')
            for route in mapper.get_routes():
                if route.match(noslash_path) is not None:
                    qs = request.query_string
                    if qs:
                        noslash_path += '?' + qs
                    return HTTPFound(location=noslash_path)
        return self.notfound_view(context, request)

def main(global_config, **settings):
	""" This function returns a Pyramid WSGI application.
	"""
	config = Configurator(
						settings=settings,
						authentication_policy=AuthTktAuthenticationPolicy(
																		secret='sekrit',
																		callback=groupfinder,
																		timeout=1200,
																		reissue_time=120),
						session_factory = my_session_factory,
						)

	config.add_static_view('static', 'static', cache_max_age=3600)
	#config.add_route('mail_icon', '/mail_icon.png')
	
	#working
	
	#config.add_route('test', '/test')
	config.add_route('register', '/register')
	config.add_route('login', '/login')
	config.add_route('logout', '/logout')
	
	config.add_route('replays', '/replays')
	config.add_route('comments', '/replays/{replay_id}/comments')
	config.add_route('reviews', '/replays/{replay_id}/reviews')
	config.add_route('ask_for_review', '/replays/{replay_id}/ask-for-review')
	config.add_route('save_reviewee_comment', '/replays/{replay_id}/save-reviewee-comment')
	config.add_route('save_reviewer_comment', '/replays/{replay_id}/save-reviewer-comment')
	
	
	config.add_route('your_replays', '/your-replay-stuff/replays')
	config.add_route('your_reviewed_replays', '/your-replay-stuff/reviewed-replays')
	
	config.add_route('reviews_asked_of_you', '/your-review-stuff/reviews-asked-of-you')
	config.add_route('reviews_asked_of_others', '/your-review-stuff/reviews-asked-of-others')
	config.add_route('reviews_by_you', '/your-review-stuff/reviews-by-you')
	config.add_route('reviews_by_others', '/your-review-stuff/reviews-by-others')
	
	config.add_route('faq', '/faq')
	config.add_route('post_comment', '/replays/{replay_id}/post_comment')
	
	
	config.add_route('download_replay', '/replays/{replay_id}/download')
#	config.add_route('your_replays', '/your-replay-stuff/replays')
#	config.add_route('yourreplaystuff-replays-replay_id-comments', '/your-replay-stuff/replays/{replay_id}/comments')
#	config.add_route('yourreplaystuff-replays-replay_id-reviews', '/your-replay-stuff/replays/{replay_id}/reviews')
#	config.add_route('save_owner_comment', '/save_owner_comment/{replay_id}')
	
	
#	config.add_route('yourreviewstuff-reviewsaskedofyou', '/your-review-stuff/reviews-asked-of-you')
#	config.add_route('yourreviewstuff-reviewsaskedofothers', '/your-review-stuff/reviews-asked-of-others')
					 
	config.add_route('upload', '/upload')
#	config.add_route('ask_for_review', '/ask_for_review/{replay_id}')
	config.add_route('upload_replay', '/upload_replay')
	# replays view
	
#	config.add_route('your_replays', '/your-replay-stuff/replays') # logged in
#	config.add_route('your_reviewed_replays', '/your-replay-stuff/reviewed-replays/') # logged in
#	
#	# replay view
#	config.add_route('replay', '/replays/{replay_id}')
#	config.add_route('your_replay', '/your-replay-stuff/replays/{replay_id}') # logged in
#	config.add_route('your_reviewed_replay', '/your-replay-stuff/reviewed-replays/{replay_id}') # logged in
#	config.add_route('your_review', '/your-review-stuff/reviews/{replay_id}') # logged in
#	
#	# redirect to 'your_replays'
#	config.add_route('your_replay_stuff', '/your-replay-stuff') # logged in
#	# redirect to 'replays_to_review'
#	config.add_route('your_review_stuff', '/your-review-stuff') # logged in
#	
#	# feed view
#	config.add_route('your_reviews', '/your-review-stuff/reviews') # logged in
#	config.add_route('your_replays_to_review', '/your-review-stuff/replays-to-review') # logged in
#	config.add_route('reviews_you_are_waiting_for', '/your-review-stuff/reviews-you-are-waiting-for') # logged in
#	config.add_route('notifications', '/your-notifications') # logged in
#	
#	# general view
#	config.add_route('faq', '/faq')
#	config.add_route('feedback', '/feedback')
#	config.add_route('upload', '/upload') # redirect to login/register if not logged in
#	config.add_route('register', '/register')
#	config.add_route('login', '/login')
#	
#	# actions
	#config.add_route('comment_on_replay', '/replays/{replay_id}/comment')
#	config.add_route('upload_replay', '/upload_replay')

#	config.add_route('logout', '/logout')
	
	# reverse slash append
	config.add_notfound_view(RemoveSlashNotFoundViewFactory())
	
	config.scan()
	
	return config.make_wsgi_app()
