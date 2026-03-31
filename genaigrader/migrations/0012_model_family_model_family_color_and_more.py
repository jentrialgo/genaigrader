import colorsys
import hashlib
import math
import re

from django.db import migrations, models

# NOTE:
# This migration intentionally keeps its own copy of parsing/color logic instead of
# importing runtime services. Migrations must remain deterministic snapshots of
# behavior at creation time so future service refactors do not break historical
# migration execution.

SEEDED_FAMILIES = {
    "Llama": "#E312C3",
    "Qwen": "#BBCB11",
    "Deepseek": "#2C9CF0",
    "Mistral": "#F97316",
    "Gemma": "#8B5CF6",
    "Phi": "#14B8A6",
}


def _generate_color(name):
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"#{digest[:6].upper()}"


def _extract_candidate_family(description):
    value = (description or "").lower()
    parts = re.split(r"[:\-_/\s]", value)
    if parts and parts[0]:
        candidate = re.sub(r"\d+.*", "", parts[0]).strip()
        if candidate:
            return candidate.capitalize()
    return "Unknown"


def _extract_parameter_count(description):
    value = description or ""
    match_b = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?:illions)?", value)
    if match_b:
        return float(match_b.group(1))

    match_m = re.search(r"(\d+(?:\.\d+)?)\s*[mM](?:illions)?", value)
    if match_m:
        return float(match_m.group(1)) / 1000.0

    return 0


def _extract_version(description):
    value = (description or "").strip()
    if ":" in value:
        suffix = value.split(":", 1)[1].strip()
        if suffix and not re.search(r"\d+(?:\.\d+)?\s*[bBmM]", suffix):
            return suffix

    variant_parts = [p for p in re.split(r"[-_/]", value.lower()) if p]
    if variant_parts:
        trailing_variant = variant_parts[-1]
        if not re.fullmatch(r"v?\d+(?:\.\d+){0,2}", trailing_variant):
            return trailing_variant

    version_match = re.search(r"(v?\d+(?:\.\d+){0,2})", value.lower())
    if version_match:
        return version_match.group(1)

    return "default"


def _hex_to_rgb(hex_color):
    hex_color = (hex_color or "").lstrip("#")
    if len(hex_color) != 6:
        return (0.39, 0.45, 0.55)
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )


def _calculate_color_from_parameters(base_color, param_count):
    if not base_color:
        return None
    if not param_count:
        return base_color

    rgb = _hex_to_rgb(base_color)
    hue, lightness, saturation = colorsys.rgb_to_hls(rgb[0], rgb[1], rgb[2])

    log_val = max(-1.0, min(7.0, math.log2(param_count)))
    norm = (log_val + 1.0) / 8.0

    saturation = 0.85 + (norm * 0.15)
    lightness = 0.75 - (norm * 0.55)

    new_rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return _rgb_to_hex(new_rgb)


def _calculate_color_from_version(base_color, version):
    if not base_color:
        return None

    version = version or "default"
    rgb = _hex_to_rgb(base_color)
    hue, lightness, saturation = colorsys.rgb_to_hls(rgb[0], rgb[1], rgb[2])
    digest = hashlib.md5(version.encode("utf-8")).hexdigest()
    variation = int(digest[:2], 16) / 255.0

    lightness = min(0.8, max(0.25, lightness + ((variation - 0.5) * 0.35)))
    saturation = min(1.0, max(0.65, saturation + ((0.5 - variation) * 0.2)))

    new_rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return _rgb_to_hex(new_rgb)


def _is_external(model):
    return bool(model.api_url and model.api_key)


def seed_and_backfill(apps, schema_editor):
    Family = apps.get_model("genaigrader", "Family")
    Model = apps.get_model("genaigrader", "Model")

    for name, color in SEEDED_FAMILIES.items():
        Family.objects.get_or_create(name=name, defaults={"base_color": color})

    for model in Model.objects.all().iterator():
        family_name = _extract_candidate_family(model.description)
        family_obj = Family.objects.filter(name__iexact=family_name).first()
        if family_obj is None:
            family_obj = Family.objects.create(
                name=family_name,
                base_color=_generate_color(family_name),
            )
        elif not family_obj.base_color:
            family_obj.base_color = _generate_color(family_obj.name)
            family_obj.save(update_fields=["base_color"])

        model.family_id = family_obj.id

        if _is_external(model):
            model.version = _extract_version(model.description)
            computed_color = _calculate_color_from_version(
                family_obj.base_color, model.version
            )
        else:
            model.parameter_count = _extract_parameter_count(model.description)
            computed_color = _calculate_color_from_parameters(
                family_obj.base_color, model.parameter_count
            )

        current_color = (model.color or "").lower()
        family_base = (family_obj.base_color or "").lower()
        if (not current_color or current_color == family_base) and computed_color:
            model.color = computed_color

        model.save(update_fields=["family", "version", "parameter_count", "color"])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("genaigrader", "0011_alter_questionevaluation_question_option_nullable"),
    ]

    operations = [
        migrations.CreateModel(
            name="Family",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("base_color", models.CharField(blank=True, max_length=7, null=True)),
            ],
        ),
        migrations.AddField(
            model_name="model",
            name="family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="models",
                to="genaigrader.family",
            ),
        ),
        migrations.AddField(
            model_name="model",
            name="color",
            field=models.CharField(
                blank=True,
                help_text="Hex color code for the model",
                max_length=7,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="model",
            name="parameter_count",
            field=models.FloatField(
                blank=True, help_text="Model size in billions of parameters", null=True
            ),
        ),
        migrations.AddField(
            model_name="model",
            name="version",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.RunPython(seed_and_backfill, noop_reverse),
    ]
