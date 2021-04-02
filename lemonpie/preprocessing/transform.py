# AUTOGENERATED! DO NOT EDIT! File to edit: 03_preprocessing_transform.ipynb (unless otherwise specified).

__all__ = ['collate_codes_offsts', 'get_codenums_offsts', 'get_demographics', 'Patient', 'get_pckl_dir', 'PatientList',
           'cpu_cnt', 'create_all_ptlists', 'preprocess_ehr_dataset']

# Cell
from ..basics import *
from .clean import *
from .vocab import *
from fastai.imports import *
import torch.multiprocessing as multiprocessing

# Cell
def collate_codes_offsts(rec_df, age_start, age_stop, age_in_months=False):
    """Return a single patient's EmbeddingBag lookup codes and offsets for the given age span and age units"""
    codes  = []
    offsts = [0]
    age_span = age_stop - age_start
    if rec_df.empty:
        codes = ['xxnone'] * age_span
        offsts = list(range(age_span))
    else:
        for i in range(age_start, age_stop, 1):
            if age_in_months: res = (rec_df.code[rec_df.age_months == i]).values
            else            : res = (rec_df.code[rec_df.age == i]).values
            if len(res) > 0:
                codes.extend(res)
                if i < age_stop - 1: offsts.append(offsts[-1] + len(res))
            else:
                codes.append('xxnone')
                if i < age_stop - 1: offsts.append(offsts[-1] + 1)

    assert len(offsts) == age_span
    return codes, offsts

# Cell
def get_codenums_offsts(rec_dfs, all_vocabs, age_start, age_stop, age_in_months):
    '''Get numericalized record codes and offsets for a patient for a given age span'''
    all_codes_offsts = [collate_codes_offsts(df, age_start, age_stop, age_in_months) for df in rec_dfs]
    obs_vocab, alg_vocab, crpl_vocab, med_vocab, img_vocab, proc_vocab, cnd_vocab, imm_vocab = all_vocabs

    obs_c,  obs_o  = obs_vocab.numericalize (all_codes_offsts[0][0]), all_codes_offsts[0][1]
    alg_c,  alg_o  = alg_vocab.numericalize (all_codes_offsts[1][0]), all_codes_offsts[1][1]
    crpl_c, crpl_o = crpl_vocab.numericalize(all_codes_offsts[2][0]), all_codes_offsts[2][1]
    med_c,  med_o  = med_vocab.numericalize (all_codes_offsts[3][0]), all_codes_offsts[3][1]
    img_c,  img_o  = img_vocab.numericalize (all_codes_offsts[4][0]), all_codes_offsts[4][1]
    proc_c, proc_o = proc_vocab.numericalize(all_codes_offsts[5][0]), all_codes_offsts[5][1]
    cnd_c,  cnd_o  = cnd_vocab.numericalize (all_codes_offsts[6][0]), all_codes_offsts[6][1]
    imm_c,  imm_o  = imm_vocab.numericalize (all_codes_offsts[7][0]), all_codes_offsts[7][1]

    all_codenums = [obs_c,alg_c,crpl_c,med_c,img_c,proc_c,cnd_c,imm_c]
    all_offsts   = [obs_o,alg_o,crpl_o,med_o,img_o,proc_o,cnd_o,imm_o]

    return all_codenums, all_offsts

# Cell
def get_demographics(demograph_vector, demographics_vocabs, age_mean, age_std):
    '''Numericalize demographics and normalize age for a given patient'''
    bday, bmonth, byear, marital, race, ethnicity, gender, birthplace, city, state, zipcode = demographics_vocabs
    demograph_vector = demograph_vector.fillna('xxnone')
    demographics = []

    birthdate = pd.Timestamp(demograph_vector[0])

    demographics.extend(bday.numericalize      ([birthdate.day]))
    demographics.extend(bmonth.numericalize    ([birthdate.month]))
    demographics.extend(byear.numericalize     ([birthdate.year]))
    demographics.extend(marital.numericalize   ([demograph_vector[1]]))
    demographics.extend(race.numericalize      ([demograph_vector[2]]))
    demographics.extend(ethnicity.numericalize ([demograph_vector[3]]))
    demographics.extend(gender.numericalize    ([demograph_vector[4]]))
    demographics.extend(birthplace.numericalize([demograph_vector[5]]))
    demographics.extend(city.numericalize      ([demograph_vector[6]]))
    demographics.extend(state.numericalize     ([demograph_vector[7]]))
    demographics.extend(zipcode.numericalize   ([demograph_vector[8]]))
    age = (demograph_vector[9] - age_mean) / age_std

    return demographics, age

# Cell
class Patient():
    '''Class defining a patient object that holds all numericalized / transformed data for a single patient'''
    def __init__(self, nums, offsts, demographics, age_now, birthdate, conditions, ptid):
#     def __init__(self, nums, offsts, demographics, age_now, birthdate, conditions, diabetes, stroke, alzheimers, coronaryheart, ptid):
        self.obs_nums  = torch.tensor(nums[0])
        self.alg_nums  = torch.tensor(nums[1])
        self.crpl_nums = torch.tensor(nums[2])
        self.med_nums  = torch.tensor(nums[3])
        self.img_nums  = torch.tensor(nums[4])
        self.proc_nums = torch.tensor(nums[5])
        self.cnd_nums  = torch.tensor(nums[6])
        self.imm_nums  = torch.tensor(nums[7])

        self.obs_offsts  = torch.tensor(offsts[0])
        self.alg_offsts  = torch.tensor(offsts[1])
        self.crpl_offsts = torch.tensor(offsts[2])
        self.med_offsts  = torch.tensor(offsts[3])
        self.img_offsts  = torch.tensor(offsts[4])
        self.proc_offsts = torch.tensor(offsts[5])
        self.cnd_offsts  = torch.tensor(offsts[6])
        self.imm_offsts  = torch.tensor(offsts[7])

        self.demographics = torch.tensor(demographics)
        self.age_now      = torch.tensor([age_now])

        self.ptid = ptid
        self.birthdate = birthdate
        self.conditions = conditions

#         self.diabetes = diabetes
#         self.stroke = stroke
#         self.alzheimers = alzheimers
#         self.coronaryheart = coronaryheart

    def __repr__(self):
        return f'ptid:{self.ptid}, birthdate:{self.birthdate}, {list(self.conditions.items())[:2]}.., device:{self.alg_nums.device}'

    @classmethod
    def create(cls, rec_dfs, demograph, vocablist, ptid, birthdate, conditions, age_start, age_stop, age_in_months):
#     def create(cls, rec_dfs, demograph, vocablist, ptid, birthdate, conditions, diabetes, stroke, alzheimers, coronaryheart, age_start, age_stop, age_in_months):
        '''Lookup codes, numericalize and then create patient object - given a patient id'''
        codenums, offsts  = get_codenums_offsts(rec_dfs, vocablist.records_vocabs, age_start, age_stop, age_in_months)
        demographics, age_now = get_demographics(demograph, vocablist.demographics_vocabs, vocablist.age_mean, vocablist.age_std)
#         return cls(codenums, offsts, demographics, age_now, birthdate, conditions, diabetes, stroke, alzheimers, coronaryheart, ptid)
        return cls(codenums, offsts, demographics, age_now, birthdate, conditions, ptid)

    def pin_memory(self):
        '''Call `torch.Tensor.pin_memory` for (all tensors of) this patient object'''
        if not self.obs_nums.is_pinned():
            self.obs_nums  = self.obs_nums.pin_memory()
            self.alg_nums  = self.alg_nums.pin_memory()
            self.crpl_nums = self.crpl_nums.pin_memory()
            self.med_nums  = self.med_nums.pin_memory()
            self.img_nums  = self.img_nums.pin_memory()
            self.proc_nums = self.proc_nums.pin_memory()
            self.cnd_nums  = self.cnd_nums.pin_memory()
            self.imm_nums  = self.imm_nums.pin_memory()

            self.obs_offsts  = self.obs_offsts.pin_memory()
            self.alg_offsts  = self.alg_offsts.pin_memory()
            self.crpl_offsts = self.crpl_offsts.pin_memory()
            self.med_offsts  = self.med_offsts.pin_memory()
            self.img_offsts  = self.img_offsts.pin_memory()
            self.proc_offsts = self.proc_offsts.pin_memory()
            self.cnd_offsts  = self.cnd_offsts.pin_memory()
            self.imm_offsts  = self.imm_offsts.pin_memory()

            self.demographics = self.demographics.pin_memory()
            self.age_now      = self.age_now.pin_memory()

        return self

    def to_gpu(self, non_block=False):
        '''Puts (all tensors of) this patient object on GPU'''
        self.obs_nums  = self.obs_nums.to(DEVICE, non_blocking=non_block)
        self.alg_nums  = self.alg_nums.to(DEVICE, non_blocking=non_block)
        self.crpl_nums = self.crpl_nums.to(DEVICE, non_blocking=non_block)
        self.med_nums  = self.med_nums.to(DEVICE, non_blocking=non_block)
        self.img_nums  = self.img_nums.to(DEVICE, non_blocking=non_block)
        self.proc_nums = self.proc_nums.to(DEVICE, non_blocking=non_block)
        self.cnd_nums  = self.cnd_nums.to(DEVICE, non_blocking=non_block)
        self.imm_nums  = self.imm_nums.to(DEVICE, non_blocking=non_block)

        self.obs_offsts  = self.obs_offsts.to(DEVICE, non_blocking=non_block)
        self.alg_offsts  = self.alg_offsts.to(DEVICE, non_blocking=non_block)
        self.crpl_offsts = self.crpl_offsts.to(DEVICE, non_blocking=non_block)
        self.med_offsts  = self.med_offsts.to(DEVICE, non_blocking=non_block)
        self.img_offsts  = self.img_offsts.to(DEVICE, non_blocking=non_block)
        self.proc_offsts = self.proc_offsts.to(DEVICE, non_blocking=non_block)
        self.cnd_offsts  = self.cnd_offsts.to(DEVICE, non_blocking=non_block)
        self.imm_offsts  = self.imm_offsts.to(DEVICE, non_blocking=non_block)

        self.demographics = self.demographics.to(DEVICE, non_blocking=non_block)
        self.age_now      = self.age_now.to(DEVICE, non_blocking=non_block)

        return self

# Cell
def get_pckl_dir(path, split, age_start, age_stop, age_in_months):
    '''Util function to construct pickle dir name - for persisting transformed `PatientList`s'''
    dir_name = ''
    dir_name += 'months' if age_in_months else 'years'
    dir_name += f'_{age_start}_to_{age_stop}'
    pckl_dir = Path(f'{path}/processed/{dir_name}/{split}')
    return pckl_dir

# Cell
multiprocessing.set_sharing_strategy('file_system')
cpu_cnt = int(multiprocessing.cpu_count())

class PatientList():
    '''A class to hold a list of `Patient` objects'''
    def __init__(self, pts, path, split, age_start, age_stop, age_in_months):
        self.items     = pts
        self.base_path = path
        self.split     = split
        self.age_start = age_start
        self.age_stop  = age_stop
        self.age_type  = 'months' if age_in_months else 'years'

    def __len__(self): return len(self.items)
    def __iter__(self): return iter(self.items)
    def __getitem__(self, idx):
        if isinstance(idx, (int,slice)): return self.items[idx]
        if isinstance(idx[0],bool):
            assert len(idx)==len(self) # bool mask
            return [o for m,o in zip(idx,self.items) if m]
        return [self.items[i] for i in idx]
    def __repr__(self):
        res  = f'{self.__class__.__name__} ({len(self)} items)\n'
        res += f'base path:{self.base_path}; split:{self.split}; age span:{self.age_stop - self.age_start} {self.age_type}\n'
        res += f'age_start:{self.age_start}; age_stop:{self.age_stop}; age_type:{self.age_type}\n'
        for item in self.items[:10]:
            res += f'{item.__repr__()}\n'
        if len(self)>10: res = res[:-1]+ '...]'
        return res

    def _create_pts_chunk(indx_chnk, all_dfs, vocablist, cnds, pckl_dir, age_start, age_stop, age_in_months, verbose):
        '''Parallelized function to run on one core and transform a single chunk of patients and save'''

        pts = []
        for indx in indx_chnk:
            thispt = all_dfs[0].iloc[indx]
            ptid, birthdate = thispt['patient'], thispt['birthdate']
#             diabetes, stroke, alzheimers, coronaryheart = thispt['diabetes'], thispt['stroke'], thispt['alzheimers'], thispt['coronary_heart']
            conditions = {}
            for cnd in cnds:
                conditions[cnd] = thispt[cnd]

            rec_dfs = []
            for rec_df in all_dfs[2:]:
                try:
                    rec_dfs.append(rec_df.loc[[ptid]])
                except KeyError:
                    rec_dfs.append(pd.DataFrame())

            demograph = all_dfs[1].loc[ptid]
#             pts.append(Patient.create(rec_dfs, demograph, vocablist, ptid, birthdate, conditions, diabetes, stroke, alzheimers, coronaryheart, age_start, age_stop, age_in_months))
            pts.append(Patient.create(rec_dfs, demograph, vocablist, ptid, birthdate, conditions, age_start, age_stop, age_in_months))

        with open(f'{pckl_dir}/patients_{indx_chnk[0]}_{indx_chnk[-1]}.ptlist', 'wb') as pckl_f:
            pickle.dump(pts,pckl_f)

        if verbose: print(f'{multiprocessing.current_process().name}-- completed {len(indx_chnk)} patients')
        return len(pts)

    @classmethod
    def create_save(cls, all_dfs, vocablist, pckl_dir, age_start, age_stop, age_in_months, verbose=False):
        '''Function to parellelize (based on available CPU cores), transformation for all patients in given dataset and save `PatientList` object'''
        pckl_dir.mkdir(parents=True, exist_ok=True)
        indx_chnks = []

        patients_df = all_dfs[0]
        cnds=[]
        for col in (patients_df.columns[2:]):
            if '_age' not in col:
                cnds.append(col)

        total_pts = len(patients_df)
        all_indxs = np.arange(total_pts)
        chnk_sz = total_pts // (cpu_cnt-1)
        for i in range(0, total_pts, chnk_sz):
            indx_chnks.append(list(all_indxs[i:i+chnk_sz]))

        pool = multiprocessing.Pool(processes=cpu_cnt)
        parallelize = partial(cls._create_pts_chunk, all_dfs=all_dfs, vocablist=vocablist, cnds=cnds, pckl_dir=pckl_dir, age_start=age_start, age_stop=age_stop, age_in_months=age_in_months, verbose=verbose)
        all_chunks = pool.map(parallelize, indx_chnks)
        pool.close()

        print(f'{sum(all_chunks)} total patients completed, saved patient list to {pckl_dir}')

    @classmethod
    def load(cls, path, split, age_start, age_stop, age_in_months):
        '''Load previously created `PatientList` object'''
        pckl_dir = get_pckl_dir(path, split, age_start, age_stop, age_in_months)
        if not pckl_dir.exists(): raise Exception(f'"{pckl_dir}" does not exist, run pre-processing to create that dataset first.')
        ptlist = []
        for file in Path(pckl_dir).glob("*.ptlist"):
            with open(file, 'rb') as infile:
                ptlist.extend(pickle.load(infile))

        return(cls(ptlist, path, split, age_start, age_stop, age_in_months))

# Cell
def create_all_ptlists(path:Path, age_start:int, age_stop:int, age_in_months:bool, vocab_path:Path=None, verbose:bool=False, delete_existing:bool=True):
    '''Create and save `PatientList`s for train, valid and test given dataset path'''
    if vocab_path is None: vocab_path = path
    all_dfs_splits = load_cleaned_ehrdata(path) #train_dfs, valid_dfs, test_dfs
    splits = ['train', 'valid', 'test']
    vocablist = EhrVocabList.load(vocab_path)

    for all_dfs, split in zip(all_dfs_splits, splits):
        pckl_dir = get_pckl_dir(path, split, age_start, age_stop, age_in_months)
        if delete_existing:
            for file in Path(pckl_dir).glob("*.ptlist"):
                file.unlink()
        PatientList.create_save(all_dfs, vocablist, pckl_dir, age_start, age_stop, age_in_months, verbose)

# Cell
def preprocess_ehr_dataset(path, today, conditions_dict, valid_pct=0.2, test_pct=0.2, obs_vocab_buckets=5,
                           age_start=0, age_stop=20, age_in_months=False, vocab_path=None, from_raw_data=False):
    '''Util function to do all preprocessing - split & clean raw dataset, create vocab lists and create patient lists'''
    if from_raw_data:
        print('------------------- Splitting and cleaning raw dataset -------------------')
        clean_raw_ehrdata(path, valid_pct, test_pct, conditions_dict, today)
        print('------------------- Creating vocab lists -------------------')
        EhrVocabList.create(path, num_buckets=obs_vocab_buckets).save()
    else:
        print('Since data is pre-cleaned, skipping Cleaning, Splitting and Vocab-creation')

    print('------------------- Creating patient lists -------------------')
    create_all_ptlists(path, age_start, age_stop, age_in_months, vocab_path)