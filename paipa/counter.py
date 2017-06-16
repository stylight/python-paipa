import resource
import time
import logging


class Counter(object):
    """
    >>> c = Counter()
    >>> c.init("reads")
    >>> c.init("writes")
    >>> c.count("reads")
    >>> c.count("writes")
    >>> c.show()

    """
    __slots__ = ('counts', 'start', 'maxlength', 'formatstring', 'last_show',
                 'session', 'show_every', 'items', 'shows', 'quiet', 'logger')

    def __init__(self, logger=None, session=None, show_every=10, quiet=False):
        self.session = session
        if logger and isinstance(logger, (unicode, str)):
            self.logger = logging.getLogger(logger)
        elif logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger("core.pipeline")

        self.quiet = bool(quiet)
        self.items = []
        self.counts = {}
        self.start = {}
        self.show_every = show_every
        self.formatstring = ""
        self.maxlength = 0
        self.last_show = None
        self.shows = 0

    def init(self, name):
        self.items.append(name)
        self.counts[name] = 0
        self.start[name] = time.time()
        self.maxlength = max(self.maxlength, len(name))
        self.formatstring = self.formatstring + " %d/s "
        self.last_show = time.time()

    def show(self):
        if self.quiet:
            return

        message = []
        now = time.time()

        if not self.shows:
            self.shows = 25
            widths = [14] * len(self.items) + [5, 3]
            headers = zip(self.items + ["Total", "Mem"],
                          widths)

            head_msg = " | ".join(("%%%ds" % width) % header
                                  for header, width in headers)
            self.logger.debug(head_msg)

        self.shows -= 1

        total = 0
        for name in self.items:
            count = self.counts[name]
            total = count
            message.append(
                "%6d %5d/s" % (count, (count / (now - self.start[name])))
            )

        message.append("%5d" % total)

        memory_used = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        message.append("[%s]" % memory_used)
        if self.session:
            message.append("[new:%d, dirty:%d, deleted:%d, id_map:%d]" % (
                len(self.session.new),
                len(self.session.dirty),
                len(self.session.deleted),
                len(self.session.identity_map),
            ))
        self.logger.debug(" | ".join(message))

    def gauge(self, name, value):
        if name not in self.items:
            self.init(name)
        self.counts[name] = value

    def count(self, name="default", count=1):
        if name not in self.items:
            self.init(name)

        now = time.time()
        self.counts[name] += count
        if self.show_every is None:
            return

        if self.show_every == -1 or (now - self.last_show > self.show_every):
            self.show()
            self.last_show = now
