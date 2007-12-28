"""
Functions dealing with Modified Preorder Tree Traversal related setup
and creation of instance methods for a model, given the names of its
tree attributes.

``treeify`` should be the only function a user of this application need
use directly to set their model up for Modified Preorder Tree Traversal.
"""
from django.db import models
from django.db.models import signals
from django.dispatch import dispatcher

from mptt.signals import pre_delete, pre_save
from mptt.managers import TreeManager

__all__ = ['treeify', 'get_ancestors', 'get_descendants',
           'get_descendant_count']

def treeify(cls, parent_attr='parent', left_attr='lft', right_attr='rght',
            tree_id_attr='tree_id', level_attr='level',
            tree_manager_attr='tree'):
    """
    Sets the given model class up for Modified Preorder Tree Traversal,
    which involves:

    1. If any of the specified tree fields -- ``left_attr``,
       ``right_attr``, ``tree_id_attr`` and ``level_attr`` -- do not
       exist, adding them to the model class dynamically.
    2. Creating pre_save and pre_delete signal receiving functions to
       manage tree field contents.
    3. Adding tree related instance methods to the model class.
    4. Adding a custom tree ``Manager`` to the model class.
    """
    # Add tree fields if they do not exist
    for attr in [left_attr, right_attr, tree_id_attr, level_attr]:
        try:
            cls._meta.get_field(attr)
        except models.FieldDoesNotExist:
            models.PositiveIntegerField(
                db_index=True, editable=False).contribute_to_class(cls, attr)
    # Specifying weak=False is required in this case as the dispatcher
    # will be the only place a reference is held to the signal receiving
    # functions we're creating.
    dispatcher.connect(
        pre_save(parent_attr, left_attr, right_attr, tree_id_attr, level_attr),
        signal=signals.pre_save, sender=cls, weak=False)
    dispatcher.connect(pre_delete(left_attr, right_attr, tree_id_attr),
                       signal=signals.pre_delete, sender=cls, weak=False)
    setattr(cls, 'get_ancestors',
            get_ancestors(parent_attr, left_attr, right_attr, tree_id_attr))
    setattr(cls, 'get_descendants',
            get_descendants(left_attr, right_attr, tree_id_attr))
    setattr(cls, 'get_descendant_count',
            get_descendant_count(left_attr, right_attr))
    TreeManager(parent_attr, left_attr, right_attr, tree_id_attr,
                level_attr).contribute_to_class(cls, tree_manager_attr)

def get_ancestors(parent_attr, left_attr, right_attr, tree_id_attr):
    """
    Creates a function which retrieves the ancestors of a model instance
    which has the given tree attributes.
    """
    def _get_ancestors(instance, ascending=False):
        """
        Creates a ``QuerySet`` containing all the ancestors of this
        model instance.

        This defaults to being in descending order (root ancestor first,
        immediate parent last); passing ``True`` for the ``ascending``
        argument will reverse the ordering (immediate parent first, root
        ancestor last).
        """
        if getattr(instance, parent_attr) is None:
            return instance._default_manager.none()
        else:
            return instance._default_manager.filter(**{
                '%s__lt' % left_attr: getattr(instance, left_attr),
                '%s__gt' % right_attr: getattr(instance, right_attr),
                tree_id_attr: getattr(instance, tree_id_attr),
            }).order_by('%s%s' % ({True: '-', False: ''}[ascending], left_attr))
    return _get_ancestors

def get_descendants(left_attr, right_attr, tree_id_attr):
    """
    Creates a function which retrieves the descendants of a model
    instance which has the given tree attributes.
    """
    def _get_descendants(instance, include_self=False):
        """
        Creates a ``QuerySet`` containing all the descendants of this
        model instance.

        If ``include_self`` is ``True``, the ``QuerySet`` will also
        include this model instance.
        """
        filters = {tree_id_attr: getattr(instance, tree_id_attr)}
        if include_self:
            filters['%s__range' % left_attr] = (getattr(instance, left_attr),
                                                getattr(instance, right_attr))
        else:
            filters['%s__gt' % left_attr] = getattr(instance, left_attr)
            filters['%s__lt' % left_attr] = getattr(instance, right_attr)
        return instance._default_manager.filter(**filters).order_by(left_attr)
    return _get_descendants

def get_descendant_count(left_attr, right_attr):
    """
    Creates a function which determines the number of descendants of a
    model instance which has the given tree attributes.
    """
    def _get_descendant_count(instance):
        """
        Returns the number of descendants this model instance has.
        """
        return (getattr(instance, right_attr) - getattr(instance, left_attr) - 1) / 2
    return _get_descendant_count
