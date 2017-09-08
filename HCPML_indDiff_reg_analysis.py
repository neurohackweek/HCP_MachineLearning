from mvpa2.suite import *
from mvpa2.clfs.ridge import RidgeReg
from mvpa2.clfs.gpr import GPR
import os
import numpy as np
import nibabel as nib
import multiprocessing
import pandas as pd
import matplotlib.pyplot as plt
import scipy as sp

#enable output to console
verbose.level = 2

script_start_time = time.time()

#define paths
task      = 'WM' #motor, WM, gambling
clf_name  = '2bkVs0bk' #lfvslh, multiclass (all 5 movements)

data_path = os.path.join('/Volumes/maloneHD/Data/HCP_ML/', task)  # base directory (mac)
beta_path = os.path.join('/Volumes/maloneHD/Data_noSync/HCP_ML/', task, 'betas/')  # beta images
mvpa_path = os.path.join(data_path,'mvpa',clf_name)
parc_path = os.path.join(data_path,'parc') #parcellations

#analysis parameters
nsubs    = 700 #number of subjects
nparc    = 360 #number of parcels/ROIs
clf_type = 'SVM' #KNN, SVM, ridgeReg
knn_k    = round(np.sqrt(nsubs)) #k-nearest-neighbor parameter
cv_type  = 'nfld' #split_half, LOSO (leave-one-subject-out), nfld (n-fold)
targets  = ['2BK','0BK']
pe_num   = ['9']

#define subjects and mask
subs       = os.listdir(beta_path)
subs_train = subs[:nsubs]
subs_test  = subs[nsubs:nsubs+300]
surf_mask  = np.ones([1,59412]) #mask for cortical surface nodes, not subcortical/cerebellum volumetric voxels
msk_path   = os.path.join(parc_path, 'Glasser_360.dtseries.nii')
msk        = nib.load(msk_path)
msk_data   = msk.get_data()
msk_data   = msk_data[0, 0, 0, 0, 0, 0:]  #last dimension contains parcel data

#load behavioral data
df      = pd.read_csv('HCP_behavioraldata.csv')
subs    = [int(s) for s in subs_train] #convert str to int
df2     = df.loc[df['Subject'].isin(subs_train)]
acc_0bk = df2.WM_Task_0bk_Acc
acc_2bk = df2.WM_Task_2bk_Acc
acc_2bk = acc_2bk.reshape(len(subs_train),1)
acc_0bk = acc_0bk.reshape(len(subs_train),1)

#load beta imgs
ds_all = []
for index, s in enumerate(subs_train):
    tds_beta_path = os.path.join(beta_path, s,
                                 'MNINonLinear', 'Results', 'tfMRI_'+task,
                                 'tfMRI_'+task+'_hp200_s2_level2.feat',
                                 'GrayordinatesStats')
    pe_paths = []
    for p in pe_num:
        pe_path = os.path.join(tds_beta_path,
                                     'cope'+p+'.feat','pe1.dtseries.nii')

        #ds = fmri_dataset(pe_paths,targets=targets,mask=surf_mask)
        if p=='9':
            ds = fmri_dataset(pe_path, targets=acc_2bk[index])
        # elif p=='10':
        #     ds = fmri_dataset(pe_path, targets=acc_0bk[index])

        ds.sa['subject'] = np.repeat(index, len(ds))
        #ds.fa['parcel']  = msk_data
        ds_all.append(ds)
        verbose(2, "subject %i of %i loaded" % (index, nsubs))

fds = vstack(ds_all) #stack datasets


#classifier algorithm
if clf_type is 'SVM':
    clf = LinearCSVMC(tube_epsilon=0.01)
elif clf_type is 'SVM-rbf':
    clf = RbfCSVMC(tube_epsilon=0.01)
elif clf_type is 'ridgeReg':
    clf = RidgeReg()
elif clf_type is 'gpr':
    clf = GPR()

# #feature selection
# fsel = SensitivityBasedFeatureSelection(
#             OneWayAnova(),
#             FractionTailSelector(0.05, mode='select', tail='upper'))
# fclf = FeatureSelectionClassifier(clf, fsel)

#cross-validation algorithm
if cv_type is 'split_half':
    cv = CrossValidation(clf,
                         HalfPartitioner(count=2,
                                         selection_strategy='random', attr='subject'),
                         errorfx=mean_match_accuracy)
elif cv_type is 'LOSO':
    cv = CrossValidation(clf,
                         NFoldPartitioner(attr='subject'),
                         errorfx=mean_match_accuracy)
elif cv_type is 'nfld':
    cv = CrossValidation(clf,
                         NFoldPartitioner(count=5,
                                         selection_strategy='random', attr='subject'),
                         errorfx=mean_match_accuracy)


#run classification
parc       = range(1,nparc+1)
cv_results = [0 for x in parc]
num_cores  = multiprocessing.cpu_count()
#whole brain clf
cv_out = cv(fds)
#roi-wise clf
# cv_results = Parallel(n_jobs=num_cores)(delayed(runCV.runCV)
#                                         (p,fds[:, fds.fa.parcel == p],clf,cv,nparc) for p in parc)

#get feature weights
sensana = clf.get_sensitivity_analyzer()
sens    = sensana(fds)

#convert feature weights to numpy array and save
sens_out = np.asarray(sens)
np.save(os.path.join(mvpa_path,'cv_results',str(nsubs)+'subs_'+cv_type+'_CV_'+clf_type+'reg_ftrWghts'),
        sens_out)


#feature weights x 2bk beta image
dp = np.zeros([len(subs_test),1])
for index, s in enumerate(subs_test):
    path = os.path.join(beta_path, s,
                                 'MNINonLinear', 'Results', 'tfMRI_'+task,
                                 'tfMRI_'+task+'_hp200_s2_level2.feat',
                                 'GrayordinatesStats','cope9.feat','pe1.dtseries.nii')
    beta_map  = nib.load(path)
    beta_map  = np.array(beta_map.dataobj)
    beta_map  = beta_map[0, 0, 0, 0, :, 0:]
    dp[index] = np.dot(sens_out,beta_map.transpose())


np.save(os.path.join(mvpa_path,'cv_results',str(nsubs)+'subs_'+cv_type+'_CV_'+clf_type+'reg_dp'),
        dp)
#np.load('/Volumes/maloneHD/Data/HCP_ML/WM/mvpa/2bkVs0bk/cv_results/700subs_nfld_CV_SVMclf_ftrWghts.npy')

#load behavioral data
subs    = [int(s) for s in subs_test] #convert str to int
df2     = df.loc[df['Subject'].isin(subs_test)]
acc_0bk = df2.WM_Task_0bk_Acc
acc_2bk = df2.WM_Task_2bk_Acc
acc_2bk = acc_2bk.reshape(len(subs_test),1)
acc_0bk = acc_0bk.reshape(len(subs_test),1)

#correlate behavior and predicted
plt.scatter(acc_2bk,dp)
corr = sp.stats.pearsonr(acc_2bk,dp)


# #feature weights x 2bk>0bk beta map
# dp = np.zeros([len(subs_test),1])
# for index, s in enumerate(subs_test):
#     path = os.path.join(beta_path, s,
#                                  'MNINonLinear', 'Results', 'tfMRI_'+task,
#                                  'tfMRI_'+task+'_hp200_s2_level2.feat',
#                                  'GrayordinatesStats','cope11.feat','pe1.dtseries.nii')
#     beta_map  = nib.load(path)
#     beta_map  = np.array(beta_map.dataobj)
#     beta_map  = beta_map[0, 0, 0, 0, :, 0:]
#     dp[index] = np.dot(sens_out,beta_map.transpose())


verbose(2, "total script computation time: %.1f minutes" % ((time.time() - script_start_time)/60))
