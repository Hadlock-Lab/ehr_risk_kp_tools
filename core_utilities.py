import requests
import pandas as pd

pd.set_option('max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', -1)

additional_name_mappings = {
    'HP:0003119': 'Abnormal circulating lipid concentration',
    'HP:0002094': 'Dyspnea',
    'HP:0100518': 'Dysuria',
    'HP:0000964': 'Eczema',
    'HP:0012378': 'Fatigue',
    'HP:0003124': 'Hypercholesterolemia',
    'HP:0002902': 'Hyponatremia',
    'HP:0100512': 'Low levels of vitamin D',
    'HP:0000132': 'Menorrhagia',
    'HP:0012203': 'Onychomycosis',
    'HP:0000938': 'Osteopenia',
    'HP:0011947': 'Respiratory tract infection',
    'HP:0001250': 'Seizure',
    'HP:0100806': 'Sepsis',
    'RXCUI:83367': 'atorvastatin',
    'RXCUI:4815': 'glyburide',
    'RXCUI:10582': 'levothyroxine',
    'RXCUI:29046': 'lisinopril',
    'RXCUI:88249': 'montelukast'
}

# EHR Risk KP endpoint
risk_kp_url = "https://api.bte.ncats.io/v1/smartapi/1bef5ecbb0b9aee90023ce9faa2c8974/query"


# Utility for creating a query
def create_query(n, e): return{"message": {"query_graph": {"nodes": n, "edges": e}}}


# Utility for getting a dictionary value if key exists
def try_get_prop(v, p): return '' if not (p in v.keys()) else v[p]


# Utility for getting a list of values if keys exist
def get_dict_props(d, props): return {p: try_get_prop(d, p) for p in props}


# Utility for getting edge attributes as a dictionary
def attr_to_dict(attrs): return {} if not (isinstance(attrs, list)) else {a['name']: a['value'] for a in attrs}


# Utility for getting equivalent identifiers of a specified type
def get_equivalent_ids(id_list, type_): return [v for k, v in [id_.split(':') for id_ in id_list] if (k == type_)]


# Utility for converting two dataframe columns to a dictionary
def get_map_from_columns(df, c1, c2): return {k: v for k, v in zip(df[c1], df[c2])}


# Function to convert node and edge properties to dataframe
def dict_to_pd(dict_, prop_list, attr_list):
    # Initialize data and specify headers
    data, headers = [], ['id_'] + prop_list + attr_list
    for k, v in dict_.items():
        # Store unique edge identifier
        props = {'id_': k}

        # Get main properties
        props.update(get_dict_props(v, prop_list))

        # Get additional properties and update props dict
        attributes = attr_to_dict(try_get_prop(v, 'attributes'))
        attributes = get_dict_props(attributes, attr_list)
        props.update(attributes)

        # Append data
        data.append([props[h] for h in headers])

    return pd.DataFrame(data, columns=headers)


# Function to add a column with equivalent ids of a specified type
def add_equivalent_id_columns(df, type_):
    # Make sure type_ is a list of strings
    type_list = type_ if isinstance(type_, list) else [type_]
    type_list = [str(t) for t in type_list]

    # Add additional columns with equivalent ids
    for t in type_list:
        # New column header
        new_col_header = t if not (t in df.columns) else "{}_equivalent".format(t)

        # Get equivalent ids of the specified type and return modified dataframe
        df[new_col_header] = [get_equivalent_ids(id_list, t) for id_list in df['equivalent_identifiers']]

    return df


def parse_query_results(response, cutoff=0.5):
    # Get query graph
    qg = response.json()['message']['query_graph']

    # Get knowledge graph
    kg = response.json()['message']['knowledge_graph']

    # Get results (node and edge bindings)
    results = response.json()['message']['results']

    # Get node properties as a dataframe
    prop_list = ['name', 'category']
    attr_list = ['equivalent_identifiers']
    node_props_df = dict_to_pd(kg['nodes'], prop_list, attr_list)

    # Add equivalent identifier columns to node properties df
    type_list = ['name', 'RXCUI', 'MONDO', 'DOID', 'HP', 'MESH', 'UMLS', 'OMIM', 'EFO']
    node_props_df = add_equivalent_id_columns(node_props_df, type_list)

    # Get edge properties as a dataframe
    prop_list = ['subject', 'predicate', 'object']
    attr_list = ['provided_by', 'api', 'MONDO', 'auc_roc', 'classifier', 'feature_coefficient', 'type']
    edge_props_df = dict_to_pd(kg['edges'], prop_list, attr_list)

    # Get node name mapping
    node_name_map = get_map_from_columns(node_props_df, 'id_', 'name')
    node_name_map.update(additional_name_mappings)

    # Add node name columns to edge properties df
    edge_props_df['subject_name'] = [try_get_prop(node_name_map, id_) for id_ in edge_props_df.subject]
    edge_props_df['object_name'] = [try_get_prop(node_name_map, id_) for id_ in edge_props_df.object]

    # Select columns of interest
    select_cols = [
        'id_', 'subject', 'predicate', 'object', 'subject_name', 'object_name',
        'feature_coefficient', 'auc_roc', 'classifier']
    edge_props_df = edge_props_df[select_cols]

    # Filter by feature_coefficient and sort
    filter_ = abs(edge_props_df.feature_coefficient) > cutoff
    edge_props_df = edge_props_df.loc[filter_]
    edge_props_df.sort_values(
        by=['subject_name', 'feature_coefficient'],
        ascending=[True, False], inplace=True)

    return edge_props_df


# Function for posting a query to the API
def post_query(query, endpoint=risk_kp_url, cutoff=0.5):
    # Post query
    response = requests.post(endpoint, json=query)
    assert (response.status_code == 200)

    # Parse results and store in dataframe
    edge_props_df = parse_query_results(response, cutoff=cutoff)

    return edge_props_df

