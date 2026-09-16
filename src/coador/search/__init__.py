"""Retrieval over a profile.

The knowledge base is a few thousand short strings, and the questions an agent
asks are identifier-shaped ("Hilt", "testInstrumentationRunner", "productFlavors")
where exact matching beats semantic similarity. So the default retriever is
lexical, in memory, and needs no model and no database.
"""

from coador.search.lexical import Hit, LexicalRetriever, search

__all__ = ["Hit", "LexicalRetriever", "search"]
