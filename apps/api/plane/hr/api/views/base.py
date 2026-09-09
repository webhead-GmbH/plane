# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared shapes for the HR endpoints.

Most of the configuration in this module is the same job over and over — list the
rows for a workspace, add one, change one, remove one — and only a manager may do
any of it. Writing that out nine times would be nine chances to leave the scoping
off one of them, so it is written once here.
"""

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.utils.company import hr_home_workspace
from plane.hr.permissions import MANAGER, SELF, hr_permission


class HrWorkspaceConfigEndpoint(BaseAPIView):
    """Manager-only configuration belonging to a workspace.

    Subclasses set ``model`` and ``serializer_class``. Every query is scoped by
    workspace here rather than in each subclass, so a missing filter is not
    something an individual endpoint can get wrong.
    """

    model = None
    serializer_class = None
    # Fields a caller may narrow the list by. Anything else in the query string is
    # ignored rather than passed through to the ORM.
    filter_fields = ()
    # Writing is always manager-only. Reading is not always: everybody needs the
    # holiday calendar and the list of absence types to use the module at all.
    read_requires_manager = True

    def get_queryset(self):
        return self.model.objects.all()

    def _apply_filters(self, queryset, request):
        for field in self.filter_fields:
            value = request.query_params.get(field)
            if value not in (None, ""):
                queryset = queryset.filter(**{field: value})
        return queryset

    def _serializer_context(self, request):
        return {"request": request}

    @hr_permission(SELF)
    def get(self, request, pk=None):
        if self.read_requires_manager and not request.hr_is_manager:
            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if pk is not None:
            row = self.get_queryset().filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)

        rows = self._apply_filters(self.get_queryset(), request)
        return Response(self.serializer_class(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def post(self, request):
        workspace = hr_home_workspace()
        serializer = self.serializer_class(data=request.data, context=self._serializer_context(request))
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(workspace=workspace)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, pk):
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(
            row, data=request.data, partial=True, context=self._serializer_context(request)
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
