"""The data the forecasts learn from, whole or as it stood on a date.

load_corpus reads every source once; Corpus.as_of(d) hides what was not yet
known on d; count_as_of reads an event's count on a forecast date from rows
dated by then.
"""
from corpus.coverage import CountAsOf, count_as_of
from corpus.load import load_corpus, read_written
from corpus.view import Corpus

__all__ = ['Corpus', 'CountAsOf', 'count_as_of', 'load_corpus', 'read_written']
