import colorsys
import hashlib
import math
import random
import re

DEFAULT_MODEL_COLOR = "#64748B"


def get_or_create_model(request):
    from genaigrader.models import Model

    model_name = request.POST.get("model", "llama3.2:1b") or "llama3.2:1b"
    model, _ = Model.objects.get_or_create(description=model_name)
    return model


def extract_model_info(description, is_external):
    if is_external:
        return (description, 0, "", "", True)

    if ":" not in description:
        return (description, 0, "", "", False)

    family, size_part = description.split(":", 1)
    size_match = re.match(r"^(\d+(?:\.\d+)?)([a-zA-Z]*)(.*)", size_part)
    if size_match:
        return (
            family,
            float(size_match.group(1)),
            size_match.group(2),
            size_match.group(3),
            False,
        )
    return (family, 0, "", size_part, False)


def parse_candidate_family(description):
    # Keep separator set aligned with migration 0012 parser.
    parts = re.split(r"[:\-_/\s]", (description or "").lower())
    if parts and parts[0]:
        candidate = re.sub(r"\d+.*", "", parts[0]).strip()
        if candidate:
            return candidate
    return "unknown"


def parse_version(description):
    model_name = description or ""
    if ":" in model_name:
        suffix = model_name.split(":", 1)[1].strip()
        if suffix and not re.search(r"\d+(?:\.\d+)?\s*[bBmM]", suffix):
            return suffix

    variant_parts = [p for p in re.split(r"[-_/]", model_name.lower()) if p]
    if variant_parts:
        trailing_variant = variant_parts[-1]
        if not re.fullmatch(r"v?\d+(?:\.\d+){0,2}", trailing_variant):
            return trailing_variant

    version_match = re.search(r"(v?\d+(?:\.\d+){0,2})", model_name.lower())
    return version_match.group(1) if version_match else "default"


def parse_parameter_count(description, is_external):
    _, size_value, size_unit, _, _ = extract_model_info(description, is_external)
    if size_value <= 0:
        return None
    return size_value / 1000.0 if size_unit.lower() == "m" else size_value


def color_from_name(name):
    digest = hashlib.md5((name or "unknown").encode("utf-8")).hexdigest()
    return f"#{digest[:6].upper()}"


def find_matching_family(candidate_family):
    from genaigrader.models import Family

    candidate_lower = candidate_family.lower()
    existing_families = (
        Family.objects.exclude(name__isnull=True)
        .exclude(name__exact="")
        .order_by("name")
        .values_list("name", flat=True)
        .distinct()
    )

    best_match = None
    best_score = None
    for existing_family in existing_families:
        existing_lower = existing_family.lower()
        if existing_lower == candidate_lower:
            # Highest priority: exact case-insensitive family match.
            score = (0, len(existing_family), existing_lower)
        elif parse_candidate_family(existing_family) == candidate_lower:
            # Fallback: same canonical candidate after normalization.
            score = (1, len(existing_family), existing_lower)
        else:
            continue

        if best_score is None or score < best_score:
            best_score = score
            best_match = existing_family

    return best_match


def hex_to_rgb(hex_color):
    value = (hex_color or "").lstrip("#")
    if len(value) != 6:
        return (0.39, 0.45, 0.55)
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )


def is_color_distinct(new_color, min_distance=30):
    from genaigrader.models import Family

    existing_families = (
        Family.objects.exclude(base_color__isnull=True)
        .exclude(base_color__exact="")
        .values_list("base_color", flat=True)
        .distinct()
    )

    new_hls = colorsys.rgb_to_hls(*hex_to_rgb(new_color))
    for existing_color in existing_families:
        existing_hls = colorsys.rgb_to_hls(*hex_to_rgb(existing_color))
        hue_diff = abs(new_hls[0] - existing_hls[0]) * 360
        hue_diff = min(hue_diff, 360 - hue_diff)
        if hue_diff < min_distance:
            return False
    return True


def generate_distinct_color():
    for _ in range(50):
        hue = random.random()
        saturation = random.uniform(0.6, 0.9)
        lightness = random.uniform(0.45, 0.60)
        hex_color = rgb_to_hex(colorsys.hls_to_rgb(hue, lightness, saturation))
        if is_color_distinct(hex_color):
            return hex_color
    return "#" + "".join(random.choice("0123456789ABCDEF") for _ in range(6))


def calculate_color_from_parameters(base_color, param_count):
    if not base_color:
        return None
    if param_count is None or param_count == 0:
        return base_color

    hue, lightness, saturation = colorsys.rgb_to_hls(*hex_to_rgb(base_color))
    log_val = max(-1.0, min(7.0, math.log2(param_count)))
    norm = (log_val + 1.0) / 8.0
    saturation = 0.85 + (norm * 0.15)
    lightness = 0.75 - (norm * 0.55)
    return rgb_to_hex(colorsys.hls_to_rgb(hue, lightness, saturation))


def calculate_color_from_version(base_color, version):
    if not base_color:
        return None
    if not version:
        return base_color

    hue, lightness, saturation = colorsys.rgb_to_hls(*hex_to_rgb(base_color))
    digest = hashlib.md5(version.encode("utf-8")).hexdigest()
    variation = int(digest[:2], 16) / 255.0
    lightness = min(0.8, max(0.25, lightness + ((variation - 0.5) * 0.35)))
    saturation = min(1.0, max(0.65, saturation + ((0.5 - variation) * 0.2)))
    return rgb_to_hex(colorsys.hls_to_rgb(hue, lightness, saturation))


def needs_model_color_refresh(model_obj):
    if not model_obj.color:
        return True
    if model_obj.family and model_obj.family.base_color:
        return model_obj.color.lower() == model_obj.family.base_color.lower()
    return False


def resolve_model_color(model_obj):
    return getattr(model_obj, "color", None) or DEFAULT_MODEL_COLOR


def get_or_create_family(candidate_family):
    from genaigrader.models import Family

    matching_family = find_matching_family(candidate_family)
    family_name = matching_family if matching_family else candidate_family.capitalize()

    family_obj, _ = Family.objects.get_or_create(name=family_name)
    if not family_obj.base_color:
        family_obj.base_color = generate_distinct_color()
        family_obj.save(update_fields=["base_color"])
    return family_obj


def auto_classify_and_color(model_obj):
    candidate_family = parse_candidate_family(model_obj.description)
    if model_obj.family is None:
        model_obj.family = get_or_create_family(candidate_family)

    base_color = model_obj.family.base_color or generate_distinct_color()
    if not model_obj.family.base_color:
        model_obj.family.base_color = base_color
        model_obj.family.save(update_fields=["base_color"])

    needs_color_refresh = needs_model_color_refresh(model_obj)

    if model_obj.is_external:
        if not model_obj.version:
            model_obj.version = parse_version(model_obj.description)
        if needs_color_refresh:
            model_obj.color = calculate_color_from_version(
                base_color, model_obj.version
            )
    else:
        if model_obj.parameter_count is None:
            model_obj.parameter_count = (
                parse_parameter_count(model_obj.description, model_obj.is_external) or 0
            )
        if needs_color_refresh:
            model_obj.color = calculate_color_from_parameters(
                base_color, model_obj.parameter_count
            )
