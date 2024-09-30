from pathlib import Path
from data_utils import all_dataset

import pandas as pd


def add_valid_csv(project, release):
    # train: project@k.train.csv, test: project@k.test.csv, val: project@{k+1}.{train + test}.csv

    index_to_file_name = pd.read_csv(f"Dataset/release_dataset/{project}@{release}/mapping.csv", index_col=0, header=None).to_dict()[1]

    file_name_to_index = {v: k for k, v in index_to_file_name.items()}

    next_train = pd.read_csv(f"Dataset/release_dataset/{project}@{release+1}/train.csv", index_col=0)
    next_test = pd.read_csv(f"Dataset/release_dataset/{project}@{release+1}/test.csv", index_col=0)
    next_index_to_file_name = pd.read_csv(f"Dataset/release_dataset/{project}@{release+1}/mapping.csv", index_col=0, header=None).to_dict()[1]

    val = pd.concat([next_train, next_test])
    val = val[~val.index.duplicated(keep="first")]
    print(len(val.index))
    # Reindex by file_name and map to int
    val.index = val.index.map(lambda x: next_index_to_file_name.get(x, None))

    print(len(val.index))
    valid_index = val.index.dropna()
    val.index = val.index.map(lambda x: file_name_to_index.get(x, None))
    valid_index = val.index.dropna()
    val = val.loc[valid_index]
    print(len(val.index))

    # Drop duplicates
    val = val[~val.index.duplicated(keep="first")]

    # index type as int
    val.index = val.index.astype(int)



    val.to_csv(f"Dataset/release_dataset/{project}@{release}/valid.csv", index=True, header=True)
    


def map_indexes_to_int(train_df, test_df):
    all_files = train_df.index.append(test_df.index).unique()
    file_to_int = {file: i for i, file in enumerate(all_files)}
    int_to_file = {i: file for file, i in file_to_int.items()}  # 역매핑

    train_df.index = train_df.index.map(file_to_int)
    test_df.index = test_df.index.map(file_to_int)

    return train_df, test_df, int_to_file  # 역매핑도 반환


def remove_variables(df, vars_to_remove):
    df.drop(vars_to_remove, axis=1, inplace=True, errors="ignore")


def get_df(project: str, release: str, path_data: str = "project_dataset"):
    df = pd.read_csv(f"{path_data}/{project}/{release}", index_col=0)
    return df


def preprocess(project, releases: list[str]):
    import rpy2.robjects as ro
    from rpy2.robjects.packages import importr
    from rpy2.robjects import pandas2ri, StrVector
    dataset_trn = get_df(project, releases[0])
    dataset_tst = get_df(project, releases[1])

    duplicated_index_trn = dataset_trn.index.duplicated(keep="first")
    duplicated_index_tst = dataset_tst.index.duplicated(keep="first")

    dataset_trn = dataset_trn[~duplicated_index_trn]
    dataset_tst = dataset_tst[~duplicated_index_tst]

    print(f"Project: {project}")
    print(
        f"Release: {releases[0]} total: {len(dataset_trn)} bug: {len(dataset_trn[dataset_trn['RealBug'] == 1])}"
    )
    print(
        f"Release: {releases[1]} total: {len(dataset_tst)} bug: {len(dataset_tst[dataset_tst['RealBug'] == 1])}"
    )

    # dataset_tst에서 dataset_trn에 존재하는 동일한 인덱스와 모든 칼럼의 값이 동일한 행을 제거
    dataset_tst = dataset_tst.drop(
        dataset_tst.index[
            dataset_tst.isin(dataset_trn.to_dict(orient="list")).all(axis=1)
        ],
        errors="ignore",
    )

    vars_to_remove = ["HeuBug", "RealBugCount", "HeuBugCount"]
    remove_variables(dataset_trn, vars_to_remove)
    remove_variables(dataset_tst, vars_to_remove)

    dataset_trn = dataset_trn.rename(columns={"RealBug": "target"})
    dataset_tst = dataset_tst.rename(columns={"RealBug": "target"})

    dataset_trn["target"] = dataset_trn["target"].astype(bool)
    dataset_tst["target"] = dataset_tst["target"].astype(bool)

    dataset_trn, dataset_tst, mapping = map_indexes_to_int(dataset_trn, dataset_tst)
    Rnalytica = importr("Rnalytica")
    features_names = dataset_trn.columns.tolist()[:-1]
    X_train = dataset_trn.loc[:, features_names].copy()
    with (ro.default_converter + pandas2ri.converter).context():
        r_X_train = ro.conversion.get_conversion().py2rpy(
            X_train
        )  # rpy2의 dataframe으로 변환
    selected_features = Rnalytica.AutoSpearman(r_X_train, StrVector(features_names))
    selected_features = list(selected_features) + ["target"]
    train = dataset_trn.loc[:, selected_features]
    test = dataset_tst.loc[:, selected_features]

    return train, test, mapping


def convert_original_dataset(dataset: Path = Path("./original_dataset")):
    for csv in dataset.glob("*.csv"):
        file_name = csv.name
        project, *release = file_name.split("-")
        release = "-".join(release)
        # print(project, release)

        df = pd.read_csv(csv, index_col=0)
        df = df.drop_duplicates()

        # save to csv
        Path(f"./project_dataset/{project}").mkdir(parents=True, exist_ok=True)
        df.to_csv(f"./project_dataset/{project}/{release}")


def organize_original_dataset():
    convert_original_dataset()
    path_truncate(Path("./project_dataset/activemq"))
    path_truncate(Path("./project_dataset/hbase"))
    path_truncate(Path("./project_dataset/hive"))
    path_truncate(Path("./project_dataset/lucene"))
    path_truncate(Path("./project_dataset/wicket"))


def path_truncate(project, base="src/"):
    print(f"Project: {project.name}")
    for path in project.glob("*.csv"):
        df = pd.read_csv(path, index_col="File")
        df.index = df.index.map(lambda x: split_path(base, x))
        df.to_csv(path)


def split_path(base, path):
    if base in path:
        _, *tail = path.split(base)
        return base + base.join(tail)
    else:
        return path


def prepare_release_dataset():
    projects = all_dataset()
    for project, releases in projects.items():
        for i, release in enumerate(releases):
            dataset_trn, dataset_tst, mapping = preprocess(project, release)
            save_folder = f"release_dataset/{project}@{i}"
            Path(save_folder).mkdir(parents=True, exist_ok=True)
            dataset_trn.to_csv(save_folder + "/train.csv", index=True, header=True)
            dataset_tst.to_csv(save_folder + "/test.csv", index=True, header=True)

            # Save mapping as csv
            mapping_df = pd.DataFrame.from_dict(mapping, orient="index")
            mapping_df.to_csv(save_folder + "/mapping.csv", index=True, header=False)


if __name__ == "__main__":
    # organize_original_dataset()
    # prepare_release_dataset()
    add_valid_csv("activemq", 0)
    add_valid_csv("activemq", 1)
    add_valid_csv("activemq", 2)
    add_valid_csv("camel", 0)
    add_valid_csv("camel", 1)
    add_valid_csv("derby", 0)
    add_valid_csv("groovy", 0)
    add_valid_csv("hbase", 0)
    add_valid_csv("hive", 0)
    add_valid_csv("jruby", 0)
    add_valid_csv("jruby", 1)
    add_valid_csv("lucene", 0)
    add_valid_csv("lucene", 1)
    add_valid_csv("wicket", 0)
