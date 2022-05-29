import pytest

from gwaripper.info import children_iter_bfs, children_iter_dfs


class ParentDummy:
    def __init__(self, children):
        self.children = children


class ChildDummy:
    pass


def test_children_iter_dfs():
    # to attach to lvl3a after assert test
    lvl3e = ChildDummy()

    lvl3d = ChildDummy()
    lvl3c = ChildDummy()
    lvl3b = ChildDummy()
    lvl3a = ParentDummy([])

    lvl2d = ParentDummy([lvl3a])
    lvl2c = ChildDummy()
    lvl2b = ParentDummy([lvl3b, lvl3c, lvl3d])
    lvl2a = ChildDummy()

    lvl1e = ParentDummy([lvl2d])
    lvl1d = ChildDummy()
    lvl1c = ParentDummy([lvl2a, lvl2b, lvl2c])
    lvl1b = ChildDummy()
    lvl1a = ChildDummy()
    start = [lvl1a, lvl1b, lvl1c, lvl1d, lvl1e]

    # ignoring empty collections now
    # with pytest.raises(AssertionError):
    #     fail = [x for x in children_iter_dfs(start, file_info_only=False)]

    lvl3a.children.append(lvl3e)

    assert [x for x in children_iter_dfs(start, file_info_only=False)] == [
            (0, lvl1a), (1, lvl1b),
            (2, lvl1c),  # parent
                        (3, lvl2a),
                        (4, lvl2b),  # parent
                                    (5, lvl3b), (6, lvl3c), (7, lvl3d),
                        (8, lvl2c),
            (9, lvl1d),
            (10, lvl1e),  # parent
                        (11, lvl2d),  # parent
                                    (12, lvl3a),  # parent
                                                 (13, lvl3e)]

    assert [x for x in children_iter_dfs(start, file_info_only=False, relative_enum=True)] == [
            (0, lvl1a), (1, lvl1b),
            (2, lvl1c),  # parent
                        (0, lvl2a),
                        (1, lvl2b),  # parent
                                    (0, lvl3b), (1, lvl3c), (2, lvl3d),
                        (2, lvl2c),
            (3, lvl1d),
            (4, lvl1e),  # parent
                        (0, lvl2d),  # parent
                                    (0, lvl3a),  # parent
                                                 (0, lvl3e)]

    assert [x for x in children_iter_dfs(start, file_info_only=True)] == [
            (0, lvl1a), (1, lvl1b),
                        (2, lvl2a),
                                    (3, lvl3b), (4, lvl3c), (5, lvl3d),
                        (6, lvl2c),
            (7, lvl1d),
                                                 (8, lvl3e)]

    assert [x for x in children_iter_dfs(start, file_info_only=True, relative_enum=True)] == [
            (0, lvl1a), (1, lvl1b),
                        (0, lvl2a),
                                    (0, lvl3b), (1, lvl3c), (2, lvl3d),
                        (1, lvl2c),
            (2, lvl1d),
                                                 (0, lvl3e)]


def test_children_iter_bfs():
    # to attach to lvl3a after assert test
    lvl3e = ChildDummy()

    lvl3d = ChildDummy()
    lvl3c = ChildDummy()
    lvl3b = ChildDummy()
    lvl3a = ParentDummy([])

    lvl2d = ParentDummy([lvl3a])
    lvl2c = ChildDummy()
    lvl2b = ParentDummy([lvl3b, lvl3c, lvl3d])
    lvl2a = ChildDummy()

    lvl1e = ParentDummy([lvl2d])
    lvl1d = ChildDummy()
    lvl1c = ParentDummy([lvl2a, lvl2b, lvl2c])
    lvl1b = ChildDummy()
    lvl1a = ChildDummy()
    start = [lvl1a, lvl1b, lvl1c, lvl1d, lvl1e]

    # ignoring empty collections now
    # with pytest.raises(AssertionError):
    #     fail = [x for x in children_iter_bfs(start, file_info_only=False)]

    lvl3a.children.append(lvl3e)

    assert [x for x in children_iter_bfs(start, file_info_only=False)] == [
            (0, lvl1a), (1, lvl1b), (2, lvl1c), (3, lvl1d), (4, lvl1e),
            # parent lvl1c
            (5, lvl2a), (6, lvl2b), (7, lvl2c),
            # parent lvl1e
            (8, lvl2d),
            # parent lvl2b
            (9, lvl3b), (10, lvl3c), (11, lvl3d),
            # parent lvl2d
            (12, lvl3a),
            # parent lvl3a
            (13, lvl3e)
            ]

    assert [x for x in children_iter_bfs(start, file_info_only=False, relative_enum=True)] == [
            (0, lvl1a), (1, lvl1b), (2, lvl1c), (3, lvl1d), (4, lvl1e),
            # parent lvl1c
            (0, lvl2a), (1, lvl2b), (2, lvl2c),
            # parent lvl1e
            (0, lvl2d),
            # parent lvl2b
            (0, lvl3b), (1, lvl3c), (2, lvl3d),
            # parent lvl2d
            (0, lvl3a),
            # parent lvl3a
            (0, lvl3e)
            ]

    assert [x for x in children_iter_bfs(start, file_info_only=True)] == [
            (0, lvl1a), (1, lvl1b), (2, lvl1d),
            # parent lvl1c
            (3, lvl2a), (4, lvl2c),
            # parent lvl1e
            # parent lvl2b
            (5, lvl3b), (6, lvl3c), (7, lvl3d),
            # parent lvl2d
            # parent lvl3a
            (8, lvl3e)
            ]

    assert [x for x in children_iter_bfs(start, relative_enum=True, file_info_only=True)] == [
            (0, lvl1a), (1, lvl1b), (2, lvl1d),
            # parent lvl1c
            (0, lvl2a), (1, lvl2c),
            # parent lvl1e
            # parent lvl2b
            (0, lvl3b), (1, lvl3c), (2, lvl3d),
            # parent lvl2d
            # parent lvl3a
            (0, lvl3e)
            ]
