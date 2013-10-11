"""Instagram OAuth drop-in.
"""

import json
import logging
import urllib
import urllib2
import urlparse

import appengine_config
from python_instagram.bind import InstagramAPIError
from python_instagram.client import InstagramAPI
from webob import exc
from webutil import handlers
from webutil import models
from webutil import util

from google.appengine.ext import db
import webapp2


# instagram api url templates. can't (easily) use urllib.urlencode() because i
# want to keep the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://api.instagram.com/oauth/authorize?',
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(host_url)s/instagram/oauth_callback',
    'response_type=code',
    )))

GET_ACCESS_TOKEN_URL = 'https://api.instagram.com/oauth/access_token'


class InstagramAuth(models.KeyNameModel):
  """Datastore model class for a Instagram auth code and access token.

  The key name is the username.
  """
  auth_code = db.StringProperty(required=True)
  access_token = db.StringProperty(required=True)
  info_json = db.TextProperty(required=True)


def handle_exception(self, e, debug):
  """Exception handler that converts InstagramAPIError to HTTP errors.
  """
  if isinstance(e, InstagramAPIError):
    logging.exception(e)
    self.response.set_status(e.status_code)
    self.response.write(str(e))
  else:
    return handlers.handle_exception(self, e, debug)


class StartHandler(webapp2.RequestHandler):
  """Starts Instagram auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handlers.handle_exception

  def post(self):
    # http://instagram.com/developer/authentication/
    url = GET_AUTH_CODE_URL % {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      # TODO: CSRF protection identifier.
      'host_url': self.request.host_url,
      }
    logging.debug('Redirecting to %s', url)
    self.redirect(str(url))


class CallbackHandler(webapp2.RequestHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  handle_exception = handlers.handle_exception

  def get(self):
    if self.request.get('error'):
      params = [urllib.decode(self.request.get(k))
                for k in ('error', 'error_reason', 'error_description')]
      raise exc.HttpBadRequest('\n'.join(params))

    auth_code = self.request.get('code')
    assert auth_code

    # http://instagram.com/developer/authentication/
    data = {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      'client_secret': appengine_config.INSTAGRAM_CLIENT_SECRET,
      'code': auth_code,
      'redirect_uri': self.request.host_url + '/instagram/oauth_callback',
      'grant_type': 'authorization_code',
      }

    logging.debug('Fetching: %s with data %s', GET_ACCESS_TOKEN_URL, data)
    resp = urllib2.urlopen(GET_ACCESS_TOKEN_URL,
                           data=urllib.urlencode(data)).read()
    try:
      data = json.loads(resp)
    except ValueError, TypeError:
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Instagram response to access token request')

    if 'error_type' in resp:
      error_class = exc.status_map[data.get('code', 500)]
      raise error_class(data.get('error_message'))

    access_token = data['access_token']
    username = data['user']['username']
    InstagramAuth.get_or_insert(key_name=username, auth_code=auth_code,
                                access_token=access_token, info_json=resp)

    self.redirect('/?%s' % urllib.urlencode(
        {'instagram_username': username,
         'instagram_auth_code': util.ellipsize(auth_code),
         'instagram_access_token': util.ellipsize(access_token),
         }))


application = webapp2.WSGIApplication([
    ('/instagram/start', StartHandler),
    ('/instagram/oauth_callback', CallbackHandler),
    ], debug=appengine_config.DEBUG)