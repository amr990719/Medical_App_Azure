from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Server-side pagination for every list (PROMPT.md §45): 25 per page, at most 100."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
