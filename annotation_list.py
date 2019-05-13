from annotation import Annotation

class AnnotationList(object):

    def __init__(self, dandelion_raw_list):
        self.dandelion_raw_list = dandelion_raw_list
        self.good_annotations = []

        for annotation_dict in self.dandelion_raw_list.get("annotations", []):
            my_annotation = Annotation(annotation_dict)

            if not my_annotation.suppress:
                for top_entity in self.dandelion_raw_list.get("topEntities", []):
                    if my_annotation.uri == top_entity["uri"]:
                        my_annotation.is_top_entity = True
                        my_annotation.top_entity_score = top_entity["score"]
                self.good_annotations.append(my_annotation)

    @property
    def raw_annotations(self):
        return self.dandelion_raw_list["annotations"]

    def list(self):
        return self.good_annotations

    def to_dict_simple(self):
        response = [a.to_dict_simple() for a in self.good_annotations if a.confidence >= 0.65]
        return response

    def picture_candidates(self):
        response = [a.to_dict_simple() for a in self.good_annotations]
        return response