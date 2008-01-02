"""
Functions which create signal receiving functions dealing with Modified
Preorder Tree Traversal related logic for a model, given the names of
its tree attributes.
"""
from django.db import connection
from django.utils.translation import ugettext as _

from mptt.exceptions import InvalidParent

__all__ = ['pre_save', 'pre_delete']

qn = connection.ops.quote_name

def pre_save(parent_attr, left_attr, right_attr, tree_id_attr, level_attr):
    """
    Creates a pre-save signal receiver for a model which has the given
    tree attributes.
    """
    def _pre_save(instance):
        """
        If this is a new instance, sets tree fields  before it is added
        to the database, updating other nodes' edge indicators to make
        room if neccessary.

        If this is an existing instance and its parent has been changed,
        performs reparenting.
        """
        opts = instance._meta
        parent = getattr(instance, parent_attr)
        if not instance.pk:
            cursor = connection.cursor()
            db_table = qn(opts.db_table)
            if parent:
                target_right = getattr(parent, right_attr) - 1
                tree_id = getattr(parent, tree_id_attr)
                instance._tree_manager.create_space(2, target_right, tree_id)
                setattr(instance, left_attr, target_right + 1)
                setattr(instance, right_attr, target_right + 2)
                setattr(instance, tree_id_attr, tree_id)
                setattr(instance, level_attr, getattr(parent, level_attr) + 1)
            else:
                setattr(instance, left_attr, 1)
                setattr(instance, right_attr, 2)
                setattr(instance, tree_id_attr,
                        instance._tree_manager.get_next_tree_id())
                setattr(instance, level_attr, 0)
        else:
            # TODO Is it possible to track the original parent so we
            #      don't have to look it up again on each save after the
            #      first?
            old_parent = getattr(instance._default_manager.get(pk=instance.pk),
                                 parent_attr)
            if parent != old_parent:
                cursor = connection.cursor()
                db_table = qn(opts.db_table)
                if parent is None:
                    # The node used to have a parent, but it was removed
                    instance._tree_manager.make_root_node(instance)
                elif old_parent is None:
                    # The node didn't used to have a parent and has been
                    # given one.
                    instance._tree_manager.make_child_node(instance, parent)
                elif (getattr(parent, tree_id_attr) !=
                      getattr(instance, tree_id_attr)):
                    # The node's parent was changed to a node in a
                    # different tree.
                    instance._tree_manager.move_to_new_tree(instance, parent)
                else:
                    # The node's parent was changed to another node in
                    # its tree.
                    # Check the validity of the new parent
                    if (getattr(instance, left_attr)
                        <= getattr(parent, left_attr)
                        <= getattr(instance, right_attr)):
                        raise InvalidParent(_('A node may not have its parent changed to itself or any of its descendants.'))

                    tree_id = getattr(instance, tree_id_attr)
                    node_left = getattr(instance, left_attr)
                    node_right = getattr(instance, right_attr)

                    if (getattr(parent, level_attr) !=
                        getattr(old_parent, level_attr)):
                        level_change_query = """
                        UPDATE %(table)s
                        SET %(level)s = %(level)s - %%s
                        WHERE %(left)s >= %%s AND %(left)s <= %%s
                          AND %(tree_id)s = %%s""" % {
                            'table': db_table,
                            'level': qn(opts.get_field(level_attr).column),
                            'left': qn(opts.get_field(left_attr).column),
                            'tree_id': qn(opts.get_field(tree_id_attr).column),
                        }
                        level_change = (getattr(instance, level_attr) -
                                        getattr(parent, level_attr) - 1)
                        cursor.execute(level_change_query, [level_change,
                            node_left, node_right, tree_id])

                    move_subtree_query = """
                    UPDATE %(table)s
                    SET %(left)s = CASE
                        WHEN %(left)s >= %%s AND %(left)s <= %%s
                          THEN %(left)s + %%s
                        WHEN %(left)s >= %%s AND %(left)s <= %%s
                          THEN %(left)s + %%s
                        ELSE %(left)s END,
                        %(right)s = CASE
                        WHEN %(right)s >= %%s AND %(right)s <= %%s
                          THEN %(right)s + %%s
                        WHEN %(right)s >= %%s AND %(right)s <= %%s
                          THEN %(right)s + %%s
                        ELSE %(right)s END
                    WHERE %(tree_id)s = %%s""" % {
                        'table': db_table,
                        'left': qn(opts.get_field(left_attr).column),
                        'right': qn(opts.get_field(right_attr).column),
                        'tree_id': qn(opts.get_field(tree_id_attr).column),
                    }

                    parent_right = getattr(parent, right_attr)
                    subtree_width = node_right - node_left + 1
                    new_left = parent_right - subtree_width
                    new_right = parent_right - 1
                    left_boundary = min(node_left, new_left)
                    right_boundary = max(node_right, new_right)
                    left_right_change = new_left - node_left
                    gap_size = subtree_width
                    if left_right_change > 0:
                        gap_size = -gap_size

                    cursor.execute(move_subtree_query, [
                        node_left, node_right, left_right_change,
                        left_boundary, right_boundary, gap_size,
                        node_left, node_right, left_right_change,
                        left_boundary, right_boundary, gap_size,
                        tree_id])

                    # The model instance is yet to be saved, so make sure its
                    # new tree values are present.
                    setattr(instance, left_attr, new_left)
                    setattr(instance, right_attr, new_right)
                    setattr(instance, level_attr,
                            getattr(instance, level_attr) - level_change)
    return _pre_save

def pre_delete(left_attr, right_attr, tree_id_attr):
    """
    Creates a pre-delete signal receiver for a model which has the given
    tree attributes.
    """
    def _pre_delete(instance):
        """
        Updates tree node edge indicators which will by affected by the
        deletion of the given model instance and any descendants it may
        have, to ensure the integrity of the tree structure is
        maintained.
        """
        tree_width = (getattr(instance, right_attr) -
                      getattr(instance, left_attr) + 1)
        target_right = getattr(instance, right_attr)
        tree_id = getattr(instance, tree_id_attr)
        instance._tree_manager.close_gap(tree_width, target_right, tree_id)
    return _pre_delete
