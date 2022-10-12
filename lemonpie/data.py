# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/04_data.ipynb (unless otherwise specified).

__all__ = ['EHRDataSplits', 'LabelEHRData', 'EHRDataset', 'ModalityTypeBatchSampler', 'create_modality_ds_sampler',
           'MultimodalDataset', 'multimodal_collate', 'MRIDataset', 'DNADataset', 'ECGDataset', 'MultimodalEHRData']

# Cell
from .basics import *
from .preprocessing.transform import *
from fastai.imports import *
import copy, glob

# Cell
class EHRDataSplits:
    """Class to hold the PatientList splits."""

    def __init__(self, path, age_start, age_range, start_is_date, age_in_months):

        self.splits, self.modality_types = self._load_splits(
            path, age_start, age_range, start_is_date, age_in_months
        )

    def _load_splits(self, path, age_start, age_range, start_is_date, age_in_months):
        """Load splits of preprocessed `PatientList`s from persistent store using path."""
        splits = {}
        modality_types = {}
        for split in ["train", "valid", "test"]:
            pckl_dir = get_pckl_dir(
                path, split, 999, age_start, age_range, age_in_months
            )
            mod_types = [
                mod_type.name.split("_")[-1] for mod_type in pckl_dir.parent.iterdir()
            ]

            modality_types[split] = mod_types
            splits[split] = [
                PatientList.load(
                    path=path,
                    split=split,
                    modality_type=m_type,
                    age_start=age_start,
                    age_range=age_range,
                    start_is_date=start_is_date,
                    age_in_months=age_in_months,
                )
                for m_type in mod_types
            ]

        return splits, modality_types

    def get_splits_modtypes(self):
        """Return splits and modality types."""
        return self.splits, self.modality_types

    def get_lengths(self):
        """Return a dataframe with lengths (# of patients) of the splits (train, valid, test) and total."""
        lengths = []
        train, valid, test = self.splits.values()

        for split in [train, valid, test]:
            lengths.append(sum([len(ptlist) for ptlist in split]))
        lengths.append(sum(lengths))
        return pd.DataFrame(
            lengths, index=["train", "valid", "test", "total"], columns=["lengths"]
        )

    def get_label_counts(self, labels):
        """Get prevalence counts of labels in each split
        returns a dataframe with counts for each split and total count."""

        train, valid, test = self.splits.values()

        # flatten for each split
        train_ptlist = [ptlist for mod_type in train for ptlist in mod_type]
        valid_ptlist = [ptlist for mod_type in valid for ptlist in mod_type]
        test_ptlist = [ptlist for mod_type in test for ptlist in mod_type]

        counts = []
        for label in labels:
            train_count = [
                train_ptlist[i].conditions[label] == 1 for i in range(len(train_ptlist))
            ].count(True)
            valid_count = [
                valid_ptlist[i].conditions[label] == 1 for i in range(len(valid_ptlist))
            ].count(True)
            test_count = [
                test_ptlist[i].conditions[label] == 1 for i in range(len(test_ptlist))
            ].count(True)
            total_count = train_count + valid_count + test_count
            counts.append([train_count, valid_count, test_count, total_count])
        return pd.DataFrame(
            counts, index=labels, columns=["train", "valid", "test", "total"]
        )

    def get_pos_wts(self, labels):
        """Get positive weights to be used in `nn.BCEWithLogitsLoss`."""
        pos_counts = self.get_label_counts(labels)
        neg_counts = self.get_lengths().transpose().values - pos_counts
        return round(neg_counts / pos_counts)


# Cell
class LabelEHRData():
    '''Class to hold labeled EHR data splits'''
    def __init__(self, train, valid, test, labels):
        '''Extracts y from patient object, each labelset a tuple of x,y: x=Patient object, y=tensor of conditions'''
        self.x_train, self.y_train = train, self._get_y(train, labels)
        self.x_valid, self.y_valid = valid, self._get_y(valid, labels)
        self.x_test,  self.y_test  = test , self._get_y(test , labels)

        self.train = self.x_train, self.y_train
        self.valid = self.x_valid, self.y_valid
        self.test  = self.x_test,  self.y_test

    def _get_y(self, ds, labels):
        '''Extract y from each patient object in ds and stack them - ds is dataset containing patient objects'''
        y = []
        for pt in ds:
            y.append( torch.FloatTensor(np.array([pt.conditions[label] for label in labels], dtype='float')) )
        return torch.stack(y)

# Cell
class EHRDataset(torch.utils.data.Dataset):
    """Class to hold a single EHR dataset (holds a tuple of x, y & m for modality type).
    Also handles lazy vs full loading of dataset on GPU."""

    def __init__(
        self,
        ptlist: list,
        labels: list,
        modality_type: int,
        lazy_load_gpu: bool = True,
    ):
        """Extract y, create x,y: x=Patient object, y=tensor of conditions
        If `lazy_load_gpu` is `False`, load entire dataset on GPU."""

        self.x, self.y = ptlist, self._get_y(ptlist, labels)
        # self.m = torch.full((len(ptlist), 1), modality_type)
        self.m = modality_type
        self.lazy = lazy_load_gpu

        if self.lazy == False:
            self.x = [pt.to_gpu() for pt in self.x]
            self.y = self.y.to(DEVICE)
            self.m = self.m.to(DEVICE)

    def _get_y(self, ptlist, labels):
        """Extract y from each patient object in ptlist and stack them."""
        y = []
        for pt in ptlist:
            y.append(
                torch.FloatTensor(
                    np.array([pt.conditions[label] for label in labels], dtype="float")
                )
            )
        return torch.stack(y)

    def __len__(self):
        return len(self.x)

    def _test_getitem(self, i):
        return self.x[i], self.y[i], self.m

    def __getitem__(self, i):
        """If lazy loading, return deep copy of patient object `i`
        else entire dataset already on GPU - just return `i`."""
        if self.lazy:
            return copy.deepcopy(self.x[i]), self.y[i], self.m  # make m[i] if tensor
        else:
            return self.x[i], self.y[i], self.m


# Cell


class ModalityTypeBatchSampler(Sampler):
    """Custom BatchSampler for multimodal data."""

    def __init__(self, indices_list: list, batch_size: int, shuffle: bool):
        """Init with indicies from every modality-type dataset and create all batches."""
        self.indices_list = indices_list
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.all_batches = self._create_batches()

    def _chunk(self, indices, size):
        """Chunk indices into batch size."""
        return torch.split(torch.tensor(indices), size)

    def _create_batches(self):
        """Create batches."""
        all_batches = []
        for indices in self.indices_list:
            if self.shuffle:
                random.shuffle(indices)
            all_batches.extend(self._chunk(indices, self.batch_size))
        all_batches = [batch.tolist() for batch in all_batches]

        return all_batches

    def __iter__(self):
        """Iterable used by dataloaders."""
        if self.shuffle:
            random.shuffle(self.all_batches)
        return iter(self.all_batches)

    def __len__(self):
        """Return length based on concated datasets."""
        return len(self.all_batches)


# Cell
def create_modality_ds_sampler(
    ehr_dataset_list: list, batch_size: int, shuffle: bool
):
    """Create a custom ConcatDataset and BatchSampler for modality types."""

    modtype_dataset = torch.utils.data.ConcatDataset(ehr_dataset_list)
    indxs = modtype_dataset.cumulative_sizes

    indicies_list = []
    for i in range(len(ehr_dataset_list)):
        if i == 0:
            indx_range = range(indxs[0])
        else:
            indx_range = range(indxs[i - 1], indxs[i])
        indicies_list.append(list(indx_range))

    batch_sampler = ModalityTypeBatchSampler(indicies_list, batch_size, shuffle)

    return modtype_dataset, batch_sampler


# Cell
class MultimodalDataset(torch.utils.data.Dataset):
    """Multimodal dataset for EHR plus other modalities."""

    def __init__(self, ds_list):
        """Separate EHR and other modalities."""
        self.ehr_ds = ds_list[0]
        if len(ds_list) > 1:
            self.other_ds_list = ds_list[1:]

    def __getitem__(self, i):
        """Get patient_ids from EHRDataset and
        use them to fetch data of other modalities."""

        ehr = self.ehr_ds[i]
        patient = ehr[0]
        ptid = patient.ptid
        if hasattr(self, "other_ds_list"):
            if len(self.other_ds_list) == 1:
                return ehr, self.other_ds_list[0][ptid]
            else:
                return ehr, tuple(ds[ptid] for ds in self.other_ds_list)
        else:
            return ehr, None

    def __len__(self):
        """Return count of patients in this modality type."""
        return len(self.ehr_ds)


# Cell
def multimodal_collate(batch):
    """Custom collate fn for EHR plus 3 other modalities."""
    batch_out = {}
    ehr, other = zip(*batch)
    pts, ys, ms = zip(*ehr)
    batch_out["patients"] = pts
    batch_out["ys"] = torch.stack(ys)

    if ms[0] == 0:
        return batch_out


    elif ms[0] == 1:
        batch_out["mri"] = torch.stack(other)

    elif ms[0] == 10:
        batch_out["dna"] = torch.stack(other)

    elif ms[0] == 11:
        mri_input, dna_input = zip(*other)
        batch_out["mri"] = torch.stack(mri_input)
        batch_out["dna"] = torch.stack(dna_input)

    elif ms[0] == 20:
        batch_out["ecg"] = torch.stack(other)

    elif ms[0] == 21:
        mri_input, ecg_input = zip(*other)
        batch_out["mri"] = torch.stack(mri_input)
        batch_out["ecg"] = torch.stack(ecg_input)

    elif ms[0] == 30:
        dna_input, ecg_input = zip(*other)
        batch_out["dna"] = torch.stack(dna_input)
        batch_out["ecg"] = torch.stack(ecg_input)

    elif ms[0] == 31:
        mri_input, dna_input, ecg_input = zip(*other)
        batch_out["mri"] = torch.stack(mri_input)
        batch_out["dna"] = torch.stack(dna_input)
        batch_out["ecg"] = torch.stack(ecg_input)

    else:
        raise Exception(f"Unrecognized modality type {ms[0]}.")

    return batch_out


# Cell

class MRIDataset(torch.utils.data.Dataset):
    def __init__(self, datastore: str, tensor_sz: tuple):
        super().__init__()
        self.mri_dir = f"{datastore}/output/dicom"
        self.tensor_sz = tensor_sz

    def __getitem__(self, i):
        mri_fname = glob.glob(f"{self.mri_dir}/*{i}*")
        if len(mri_fname) == 1:
            return torch.full(self.tensor_sz, 1)
        else:
            raise Exception(f"MRI filename match error - found {len(mri_fname)} files with ptid: {i}.")

    def __len__(self):
        return 1


# Cell

class DNADataset(torch.utils.data.Dataset):
    def __init__(self, datastore: str, tensor_sz: tuple):
        super().__init__()
        self.dna_dir = f"{datastore}/output/dna"
        self.tensor_sz = tensor_sz

    def __getitem__(self, i):
        dna_fname = glob.glob(f"{self.dna_dir}/*{i}*")
        if len(dna_fname) == 1:
            return torch.full(self.tensor_sz, 10)
        else:
            raise Exception(f"DNA filename match error - found {len(dna_fname)} files with ptid: {i}.")

    def __len__(self):
        return 1


# Cell

class ECGDataset(torch.utils.data.Dataset):
    def __init__(self, datastore: str, tensor_sz: tuple):
        super().__init__()
        ecg_data = pd.read_csv(f"{datastore}/ecg.csv")
        self.ecg_pids = ecg_data.patient.unique()
        self.tensor_sz = tensor_sz

    def __getitem__(self, i):

        if i in self.ecg_pids:
            return torch.full(self.tensor_sz, 20)
        else:
            raise Exception(f"ptid: {i} - not found in ECG data.")

    def __len__(self):
        return 1


# Cell
class MultimodalEHRData:
    """All encompassing class for Multimodal EHR data.
    Holds Splits, Datasets, & DataLoaders."""

    def __init__(
        self,
        path,
        labels,
        age_start,
        age_range,
        start_is_date,
        age_in_months,
        lazy_load_gpu=True,
    ):
        self.path, self.labels = path, labels
        self.age_start, self.age_range = age_start, age_range
        self.start_is_date, self.age_in_months = start_is_date, age_in_months
        self.lazy_load_gpu = lazy_load_gpu

    def load_splits(self):
        """Load data splits given dataset path."""
        self.data_splits = EHRDataSplits(
            self.path,
            self.age_start,
            self.age_range,
            self.start_is_date,
            self.age_in_months,
        )
        self.splits, self.modality_types = self.data_splits.get_splits_modtypes()

    def get_dls(self, batch_size: int, num_workers: int, collate_fn: str):
        """Create and return `DataLoader`s for train, valid and test."""
        dls = {}
        for split in ["train", "valid", "test"]:

            ptlists = self.splits[split]
            mod_types = self.modality_types[split]
            assert len(ptlists) == len(
                mod_types
            ), f"Unequal lengths - ptlists:{len(ptlists)} != modality_types:{len(mod_types)} in {split}."

            multimodal_ds_list = []
            for ptlist, mod_type in zip(ptlists, mod_types):
                mod_type = int(mod_type)
                unimodal_ds_list = []

                # EHR
                unimodal_ds_list.append(
                    EHRDataset(
                        ptlist=ptlist, labels=self.labels, modality_type=mod_type
                    )
                )
                # + MRI
                if mod_type in [1, 11, 21, 31]:
                    unimodal_ds_list.append(MRIDataset(self.path, (4, 4)))
                # + DNA
                if mod_type in [10, 11, 30, 31]:
                    unimodal_ds_list.append(DNADataset(self.path, (3, 2)))
                # + ECG
                if mod_type in [20, 21, 30, 31]:
                    unimodal_ds_list.append(ECGDataset(self.path, (5,)))

                multimodal_ds_list.append(MultimodalDataset(unimodal_ds_list))

            shuffle = True if split == "train" else False
            ds, sampler = create_modality_ds_sampler(
                multimodal_ds_list, batch_size=batch_size, shuffle=shuffle
            )
            dl = DataLoader(
                dataset=ds,
                batch_sampler=sampler,
                num_workers=num_workers,
                collate_fn=collate_fn,
                pin_memory=self.lazy_load_gpu,
            )
            dls[split] = dl

        return dls

    def get_data(
        self, batch_size=64, num_workers=cpu_cnt, collate_fn=multimodal_collate
    ):
        """Return all data."""

        self.load_splits()

        dls = self.get_dls(batch_size, num_workers, collate_fn)

        pos_wts_df = self.data_splits.get_pos_wts(self.labels)
        pos_wts = {}
        pos_wts["train"] = torch.Tensor(pos_wts_df["train"].values)
        pos_wts["valid"] = torch.Tensor(pos_wts_df["valid"].values)
        pos_wts["test"] = torch.Tensor(pos_wts_df["test"].values)

        return dls, pos_wts
