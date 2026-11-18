from packages.reports.flags import FLAGS, flag_for, flag_rects


def test_every_flag_is_a_valid_hex_color_list() -> None:
    for team_id, spec in FLAGS.items():
        assert spec.kind in {"h", "v", "circle"}, team_id
        assert len(spec.colors) >= 2, team_id
        for color in spec.colors:
            assert color.startswith("#") and len(color) == 7, (team_id, color)


def test_flag_rects_cover_the_full_bounding_box_horizontal() -> None:
    rects = flag_rects(10.0, 20.0, 90.0, 60.0, "FRA")
    assert len(rects) == 3
    xs = sorted(rect[0] for rect in rects)
    assert xs[0] == 10.0
    last = max(rects, key=lambda rect: rect[0])
    assert last[0] + last[2] == 100.0
    assert all(rect[1] == 20.0 and rect[3] == 60.0 for rect in rects)


def test_flag_rects_circle_type_stays_within_bounds() -> None:
    rects = flag_rects(0.0, 0.0, 100.0, 60.0, "JPN")
    assert len(rects) == 2
    background, block = rects
    assert background == (0.0, 0.0, 100.0, 60.0, "#FFFFFF")
    block_x, block_y, block_w, block_h, _color = block
    assert 0.0 <= block_x and block_x + block_w <= 100.0
    assert 0.0 <= block_y and block_y + block_h <= 60.0


def test_unknown_team_falls_back_to_default_flag() -> None:
    from packages.reports.flags import DEFAULT_FLAG

    assert flag_for("ZZZ") == DEFAULT_FLAG
    rects = flag_rects(0.0, 0.0, 40.0, 20.0, "ZZZ")
    assert len(rects) == len(DEFAULT_FLAG.colors)
