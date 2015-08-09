from plugin.core.filters import Filters
from plugin.sync import SyncMedia, SyncData, SyncMode

from plex import Plex
import itertools
import logging

log = logging.getLogger(__name__)

TRAKT_DATA_MAP = {
    SyncMedia.Movies: [
        SyncData.Collection,
        SyncData.Playback,
        SyncData.Ratings,
        SyncData.Watched,
        # SyncData.Watchlist
    ],
    SyncMedia.Shows: [
        SyncData.Ratings
    ],
    SyncMedia.Seasons: [
        SyncData.Ratings
    ],
    SyncMedia.Episodes: [
        SyncData.Collection,
        SyncData.Playback,
        SyncData.Ratings,
        SyncData.Watched,
        # SyncData.Watchlist
    ]
}

DATA_PREFERENCE_MAP = {
    SyncData.Collection:    'sync.collection.mode',
    SyncData.Playback:      'sync.playback.mode',
    SyncData.Ratings:       'sync.ratings.mode',
    SyncData.Watched:       'sync.watched.mode',
    SyncData.Watchlist:     False,
}

class Mode(object):
    mode = None
    children = []

    def __init__(self, main):
        self.__main = main

        self.children = [c(self) for c in self.children]

    @property
    def current(self):
        return self.__main.current

    @property
    def configuration(self):
        return self.__main.current.configuration

    @property
    def handlers(self):
        return self.__main.handlers

    @property
    def modes(self):
        return self.__main.modes

    @property
    def plex(self):
        if not self.current or not self.current.state:
            return None

        return self.current.state.plex

    @property
    def trakt(self):
        if not self.current or not self.current.state:
            return None

        return self.current.state.trakt

    def run(self):
        raise NotImplementedError

    def checkpoint(self):
        if self.current is None:
            return

        self.current.checkpoint()

    def execute_children(self):
        for c in self.children:
            c.run()

    def execute_handlers(self, media, data, *args, **kwargs):
        if type(media) is not list:
            media = [media]

        if type(data) is not list:
            data = [data]

        for m, d in itertools.product(media, data):
            if d not in self.handlers:
                log.debug('Unknown sync data: %r', d)
                continue

            try:
                self.handlers[d].run(m, self.mode, *args, **kwargs)
            except Exception, ex:
                log.warn('Exception raised in handlers[%r].run(%r, ...): %s', d, m, ex, exc_info=True)

    def get_data(self, media):
        for data in TRAKT_DATA_MAP[media]:
            if not self.is_data_enabled(data):
                continue

            yield data

    def is_data_enabled(self, data):
        key = DATA_PREFERENCE_MAP.get(data)

        if key is None:
            log.warn('Unknown data: %r', data)
            return False

        if key is False:
            # Unsupported data type
            return False

        # Parse preference
        mode = self.configuration[key]

        if mode == SyncMode.Full:
            mode = [SyncMode.FastPull, SyncMode.Pull, SyncMode.Push]
        elif mode is not None:
            mode = [mode]
        else:
            mode = []

        # Check if data is enabled
        if self.mode not in mode:
            return False

        return True

    def sections(self, section_type):
        p_sections = Plex['library'].sections()

        if p_sections is None:
            return None

        # Retrieve sections
        result = []

        for section in p_sections.filter(section_type):
            # Apply section name filter
            if not Filters.is_valid_section_name(section.title):
                continue

            try:
                key = int(section.key)
            except Exception, ex:
                log.warn('Unable to cast section key %r to integer: %s', section.key, ex, exc_info=True)
                continue

            result.append((key,))

        return result


def log_unsupported_guid(logger, rating_key, p_guid, p_item, dictionary=None):
    if dictionary is not None:
        if rating_key in dictionary:
            return

        dictionary[rating_key] = True

    title = p_item.get('title')
    year = p_item.get('year')

    if title and year:
        logger.info('[%r] GUID agent %r is not supported on: %r (%r)', rating_key, p_guid.agent if p_guid else None, title, year)
    else:
        logger.info('[%r] GUID agent %r is not supported', rating_key, p_guid.agent if p_guid else None)
