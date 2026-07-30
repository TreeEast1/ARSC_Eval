"""Label definitions fixed by the BDD-OIA benchmark."""

ACTION_NAMES = ["Forward", "Stop", "Left", "Right"]

RATIONALE_NAMES = [
    "green_light",
    "follow",
    "road_clear",
    "red_light",
    "traffic_sign",
    "car",
    "person",
    "rider",
    "other_obstacle",
    "left_lane",
    "left_green_light",
    "left_follow",
    "no_left_lane",
    "left_obstacle",
    "left_solid_line",
    "right_lane",
    "right_green_light",
    "right_follow",
    "no_right_lane",
    "right_obstacle",
    "right_solid_line",
]

TARGET_RATIONALE_TO_DETECTIONS = {
    "green_light": {"traffic light"},
    "red_light": {"traffic light"},
    "left_green_light": {"traffic light"},
    "right_green_light": {"traffic light"},
    "traffic_sign": {"stop sign"},
    "car": {"car"},
    "person": {"person"},
    "rider": {"bicycle", "motorcycle"},
}

# BDD-OIA's 21 rationale labels are grouped by their associated action
# dimension in the dataset definition.  The ground-truth state of that action
# may be either positive or negative (for example, ``no_left_lane`` explains a
# negative Left decision), so validity analyses must score the probability of
# the annotated binary state rather than always using the positive class.
RATIONALE_TO_ACTION_INDEX = {
    name: action_index
    for action_index, names in enumerate(
        (
            RATIONALE_NAMES[0:3],
            RATIONALE_NAMES[3:9],
            RATIONALE_NAMES[9:15],
            RATIONALE_NAMES[15:21],
        )
    )
    for name in names
}
