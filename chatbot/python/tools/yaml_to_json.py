import json
import yaml

def yaml_file_to_json_str(yaml_file_path: str)->str:
    with open(yaml_file_path, "r",encoding='utf-8') as f:
        yaml_content = yaml.safe_load(f)
    # print(yaml_content)
    for person in yaml_content:
        print(json.dumps(person, ensure_ascii=False))
    return ""

if __name__ == "__main__":
    print(yaml_file_to_json_str("persona.yaml"))