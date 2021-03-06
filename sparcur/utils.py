import io
import os
import logging
from idlib.utils import log as _ilog
from augpathlib.utils import log as _alog
from pyontutils.utils import (makeSimpleLogger,
                              python_identifier,  # FIXME update imports
                              TZLOCAL,
                              utcnowtz,
                              isoformat,
                              isoformat_safe,
                              timeformat_friendly)
from sparcur.config import config

log = makeSimpleLogger('sparcur')
logd = log.getChild('data')
loge = log.getChild('export')

# set augpathlib log format to pyontutils (also sets all child logs)
_alog.removeHandler(_alog.handlers[0])
_alog.addHandler(log.handlers[0])
# idlib logs TODO move to pyontutils probably?
_ilog.removeHandler(_alog.handlers[0])
_ilog.addHandler(log.handlers[0])


__type_registry = {None: None}
def register_type(cls, type_name):
    if type_name in __type_registry:
        if __type_registry[type_name] is cls:
            # better to do this check here than to force
            # all callers to check for themselves which
            # can fail if two separate systems try to
            # register the same type
            return

        raise ValueError(f'Cannot map {cls} to {type_name}. Type already present! '
                         f'{type_name} -> {__type_registry[type_name]}')

    __type_registry[type_name] = cls


def register_all_types():
    # as a side effect this registers idlib streams and OntTerm
    # sigh doing anything in the top level of python :/
    import sparcur.core
    import sparcur.paths  # also a top level registration

    # this is not done at top level because it is quite slow
    from pysercomb.pyr import units as pyru
    [register_type(c, c.tag) for c in (pyru._Quant, pyru.Range)]


def fromJson(blob):
    if isinstance(blob, dict):
        if 'type' in blob:
            t = blob['type']

            if t == 'identifier':
                type_name = blob['system']
            elif t in ('quantity', 'range'):
                type_name = t
            elif t not in __type_registry:
                breakpoint()
                raise NotImplementedError(f'TODO fromJson for type {t} '
                                          f'currently not implemented\n{blob}')
            else:
                type_name = t

            cls = __type_registry[type_name]
            if cls is not None:
                return cls.fromJson(blob)

        return {k:v
                if k == 'errors' or k.endswith('_errors') else
                fromJson(v)
                for k, v in blob.items()}

    elif isinstance(blob, list):
        return [fromJson(_) for _ in blob]
    else:
        return blob


def path_irs(*paths_or_strings):
    """Given one or more paths pointing to sparcur export
    json yield the python internal representation."""
    # TODO support for urls
    import json
    register_all_types()

    for path_or_string in paths_or_strings:
        with open(path_or_string) as f:
            blob = json.load(f)

        yield fromJson(blob)


def path_ir(path_or_string):
    """Given a path or string return the sparcur python ir."""
    return next(path_irs(path_or_string))


def expand_label_curie(rows_of_terms):
    return [[value for term in rot for value in
             (term.label if term is not None else '',
              term.curie if term is not None else '')]
            for rot in rows_of_terms]


class GetTimeNow:
    def __init__(self):
        self._start_time = utcnowtz()
        self._start_local_tz = TZLOCAL()  # usually PST PDT

    @property
    def _start_time_local(self):
        return self._start_time.astimezone(self._start_local_tz)

    @property
    def START_TIMESTAMP(self):
        return isoformat(self._start_time)

    @property
    def START_TIMESTAMP_SAFE(self):
        return isoformat_safe(self._start_time)

    @property
    def START_TIMESTAMP_FRIENDLY(self):
        return timeformat_friendly(self._start_time)

    @property
    def START_TIMESTAMP_LOCAL(self):
        return isoformat(self._start_time_local)

    @property
    def START_TIMESTAMP_LOCAL_SAFE(self):
        return isoformat_safe(self._start_time_local)

    @property
    def START_TIMESTAMP_LOCAL_FRIENDLY(self):
        return timeformat_friendly(self._start_time_local)


class SimpleFileHandler:
    _FIRST = object()
    def __init__(self, log_file_path, *logs, mimic=_FIRST):
        self.log_file_handler = logging.FileHandler(log_file_path.as_posix())
        if mimic is self._FIRST and logs:
            self.mimic(logs[0])
        elif mimic:
            self.mimic(mimic)

        for log in logs:
            self(log)

    def __call__(self, *logs_to_handle):
        for log in logs_to_handle:
            log.addHandler(self.log_file_handler)

    def mimic(self, log):
        self.log_file_handler.setFormatter(log.handlers[0].formatter)


def silence_loggers(*logs):
    for log in logs:
        parent = log
        while parent:
            [parent.removeHandler(h) for h in parent.handlers]
            parent = parent.parent


def bind_file_handler(log_file):
    # FIXME the this does not work with joblib at the moment
    from idlib.utils import log as idlog
    from protcur.core import log as prlog
    from orthauth.utils import log as oalog
    from ontquery.utils import log as oqlog
    from augpathlib.utils import log as alog
    from pyontutils.utils import log as pylog
    #from blackfynn.log import get_logger; bflog = get_logger()
    #silence_loggers(bflog.parent)  # let's not

    sfh = SimpleFileHandler(log_file, log)
    sfh(alog, idlog, oalog, oqlog, prlog, pylog)#, bflog)


class _log:
    """ logging prevents nice ipython recurions error printing
        so rename this class to log when you need fake logging """
    @staticmethod
    def debug(nothing): pass
    @staticmethod
    def info(nothing): pass
    @staticmethod
    def warning(nothing): print(nothing)
    @staticmethod
    def error(nothing): pass
    @staticmethod
    def critical(nothing): pass


want_prefixes = ('TEMP', 'FMA', 'UBERON', 'PATO', 'NCBITaxon', 'ilxtr', 'sparc',
                 'BIRNLEX', 'tech', 'unit', 'ILX', 'lex',)


def is_list_or_tuple(obj):
    return isinstance(obj, list) or isinstance(obj, tuple)


def symlink_latest(dump_path, path, relative=True):
    """ relative to allow moves of the containing folder
        without breaking links """

    if relative:
        dump_path = dump_path.relative_path_from(path)

    if path.exists():
        if not path.is_symlink():
            raise TypeError(f'Why is {path.name} not a symlink? '
                            f'{path!r}')

        path.unlink()

    path.symlink_to(dump_path)


def transitive_dirs(path):
    """Fast list of all child directories using unix find."""
    command = """find -type d"""
    with path:
        with os.popen(command) as p:
            string = p.read()

    path_strings = string.split('\n')  # XXX posix path names can contain newlines
    paths = [path / s for s in path_strings if s][1:]  # leave out the parent folder itself
    return paths


class BlackfynnId(str):
    """ put all static information derivable from a blackfynn id here """
    def __new__(cls, id):
        # TODO validate structure
        self = super().__new__(cls, id)
        gotem = False
        for type_ in ('package', 'collection', 'dataset', 'organization'):
            name = 'is_' + type_
            if not gotem:
                gotem = self.startswith(f'N:{type_}:')
                setattr(self, name, gotem)
            else:
                setattr(self, name, False)

        return self

    @property
    def uri_api(self):
        # NOTE: this cannot handle file ids
        if self.is_dataset:
            endpoint = 'datasets/' + self.id
        elif self.is_organization:
            endpoint = 'organizations/' + self.id
        else:
            endpoint = 'packages/' + self.id

        return 'https://api.blackfynn.io/' + endpoint

    def uri_human(self, prefix):
        # a prefix is required to construct these
        return self  # TODO


class BlackfynnInst(BlackfynnId):
    # This isn't equivalent to BlackfynnRemote
    # because it needs to be able to obtain the
    # post pipeline data about that identifier
    @property
    def uri_human(self):
        pass
