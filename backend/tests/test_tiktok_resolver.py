import json

from backend.app.services.tiktok.resolver import _parse_hydration


def test_parse_hydration_preserves_html_entities_inside_valid_json():
    payload = {
        "__DEFAULT_SCOPE__": {
            "webapp.video-detail": {
                "itemInfo": {
                    "itemStruct": {
                        "id": "7496290066998856965",
                        "desc": "&quot;新品描述&quot;",
                    }
                }
            }
        }
    }

    parsed = _parse_hydration(json.dumps(payload, ensure_ascii=False))

    item = parsed["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]
    assert item["id"] == "7496290066998856965"
    assert item["desc"] == "&quot;新品描述&quot;"


def test_parse_hydration_falls_back_to_html_decoding_for_encoded_json():
    encoded = "{&quot;__DEFAULT_SCOPE__&quot;: {}}"

    assert _parse_hydration(encoded) == {"__DEFAULT_SCOPE__": {}}
