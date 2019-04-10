from annotation import Annotation

class AnnotationList(object):

    def __init__(self, dandelion_raw_list):
        self.dandelion_raw_list = dandelion_raw_list
        self.list_of_annotation_objects = []

        for annotation_dict in self.dandelion_raw_list["annotations"]:
            my_annotation = Annotation(annotation_dict)

            for top_entity in self.dandelion_raw_list.get("topEntities", []):
                if my_annotation.uri == top_entity["uri"]:
                    my_annotation.is_top_entity = True
                    my_annotation.top_entity_score = top_entity["score"]

            self.list_of_annotation_objects.append(my_annotation)


    @property
    def raw_annotations(self):
        return self.dandelion_raw_list["annotations"]

    def list(self):
        return self.list_of_annotation_objects

    def to_dict_simple(self):
        response = [a.to_dict_simple() for a in self.list_of_annotation_objects]
        return response

    def picture_candidates(self):
        response = [a.to_dict_simple() for a in self.list_of_annotation_objects]
        return response