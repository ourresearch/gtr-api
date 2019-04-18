import xmltodict
import json
import pickle              # import module first

# mesh tree for browsing is at https://meshb.nlm.nih.gov/treeView
# download of data is at
#  ftp://nlmpubs.nlm.nih.gov/online/mesh/MESH_FILES/xmlmesh/
#
# fp = open("/Users/hpiwowar/Downloads/desc2019.xml", "r")
# mesh_xml_snippet = fp.read()
# fp.close()
#
# parsed = xmltodict.parse(mesh_xml_snippet)
#
#
#
# f = open('/Users/hpiwowar/Downloads/desc2019.pickle', 'w')
# pickle.dump(json.dumps(parsed), f)
# f.close()
#
# print("\n")
# print(parsed.keys()[0])
#

f = open('/Users/hpiwowar/Downloads/desc2019.pickle', 'r')
file_text = pickle.load(f)
parsed = json.loads(file_text)
f.close()
print parsed.keys()[0]
mesh_dicts = parsed["DescriptorRecordSet"]["DescriptorRecord"]
sample = mesh_dicts[0:10]
simple_mesh_dicts = {}
for my_dict in mesh_dicts:
    simple_dict = {
        "descriptor_ui": my_dict["DescriptorUI"],
        "descriptor_name": my_dict["DescriptorName"]["String"]
    }
    if "TreeNumberList" in my_dict:
        tree_number = my_dict["TreeNumberList"]["TreeNumber"]
        if isinstance(tree_number, basestring):
            simple_dict["tree_number_list"] = [tree_number]
        else:
            simple_dict["tree_number_list"] = tree_number

    else:
        simple_dict["tree_number_list"] = []

    simple_mesh_dicts[my_dict["DescriptorUI"]] = simple_dict

print(len(simple_mesh_dicts))
simple_mesh_dicts.keys()[0:10]
simple_mesh_dicts["D005658"]

# print(parsed, indent=4)