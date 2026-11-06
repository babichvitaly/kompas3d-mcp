from types import SimpleNamespace as NS

from kompas_mcp import audit


def test_disconnected_feature_is_warning_despite_valid_and_no_object_error():
    feature = NS(State=272, FeatureType=104, Name="bottom", Valid=True,
                 ObjectError=0, Excluded=False, IsRollBacked=False)
    result = audit.feature_state(feature, sketch_type=5)
    assert result["status"] == "warning"
    assert result["issues"] == ["comprised_of_parts"]


def test_one_solid_body_may_have_disconnected_lumps():
    body = NS(IsSolid=True, MultiBodyParts=True,
              GetGabarit=lambda: [True, 0, 0, 0, 100, 50, 3])
    assert audit.body_state(body)["status"] == "warning"
    body.MultiBodyParts = False
    assert audit.body_state(body)["status"] == "passed"
    del body.MultiBodyParts
    assert audit.body_state(body)["status"] == "inconclusive"
