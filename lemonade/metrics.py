# AUTOGENERATED! DO NOT EDIT! File to edit: 05_metrics.ipynb (unless otherwise specified).

__all__ = ['accuracy', 'null_accuracy', 'ROC', 'MultiLabelROC', 'plot_rocs', 'plot_train_valid_rocs', 'auroc_score',
           'auroc_ci']

# Cell
from .setup import *
from fastai.imports import *
from sklearn import metrics as skl_metrics, preprocessing as skl_preproc

# Cell
def accuracy(y:'y_true', yhat:'yhat_prob', threshold:float=0.5) -> float:
    '''Accuracy (percentage of correct predictions) for binary classification'''
    return ((yhat>threshold) == y).float().mean()

# Cell
def null_accuracy(y:'y_true') -> float:
    '''Null accuracy for binary classification: accuracy that could be achieved by always predicting the most frequent class'''
    null_mean = y.float().mean()
    return max(null_mean, 1-null_mean)

# Cell
class ROC:
    '''Class to hold Receiver Operating Characteristic (ROC) and AUROC (area under ROC curve) score for a single class'''
    def __init__(self, y, yhat):
        self.fpr, self.tpr, self.thresholds = skl_metrics.roc_curve(y, yhat)
        self.auroc = skl_metrics.roc_auc_score(y, yhat)

    def optimal_thresh(self):
        '''Calculate optimal threshold (on ROC curve) for a single class'''
        opt_idx = np.argmin(np.sqrt(np.square(1-self.tpr) + np.square(self.fpr)))
        return self.thresholds[opt_idx]

    def plot(self, label, title):
        '''Plot ROC curve for a single class'''
        plot_rocs([self], labels=[label], title=title)

# Cell
class MultiLabelROC:
    '''Class that holds `ROC` objects for multiple classes'''
    def __init__(self, y, yhat, labels):
        self.labels = labels
        self.ROCs = dict()
        for i in range(len(labels)):
            self.ROCs[labels[i]] = ROC(y[:, i], yhat[:, i])

    def plot(self, title):
        '''Plot multiple ROC curves in a single plot'''
        plot_rocs(self.ROCs, labels=self.labels, title=title, multilabel=True)

# Cell
def plot_rocs(ROCs, labels, title='ROC curve', multilabel=False, axis=None):
    '''Plot one (single-label) or multiple (multi-label) ROC curves'''
    if axis == None:
        fig = plt.figure(figsize=(8,5))
        axis = fig.add_axes([0,0,1,1])
    for i in range(len(ROCs)):
        if multilabel: axis.plot(ROCs[labels[i]].fpr, ROCs[labels[i]].tpr, label=f'{labels[i]} - {ROCs[labels[i]].auroc:0.3f}')
        else: axis.plot(ROCs[i].fpr, ROCs[i].tpr, label=f'{labels[i]} - {ROCs[i].auroc:0.3f}')
    axis.set_xlim([0.0, 1.0])
    axis.set_ylim([0.0, 1.0])
    axis.set_title(title)
    axis.set_xlabel('False Positive Rate (1 - Specificity)')
    axis.set_ylabel('True Positive Rate (Sensitivity)')
    axis.legend(loc="lower right")
    axis.grid(True)

# Cell
def plot_train_valid_rocs(train_ROC, valid_ROC, labels, multilabel=False):
    '''Convenience fn to plot train and valid ROC curves side by side'''
    if multilabel:
        fig, axes = plt.subplots(1,2, figsize=(15,5))
        plt.tight_layout()
        plot_rocs(train_ROC, labels, title='Train ROC curves', multilabel=True, axis=axes[0])
        plot_rocs(valid_ROC, labels, title='Valid ROC curves', multilabel=True, axis=axes[1])
    else:
        plot_rocs([train_ROC, valid_ROC], ['train', 'valid'], title='Train & Valid ROC Curves')

# Cell
def auroc_score(y, yhat, average=None):
    '''Return scikit_learn auroc score'''
    return skl_metrics.roc_auc_score(y, yhat, average=average)

# Cell
def auroc_ci(y, yhat):
    '''Returns 95% confidence interval for auroc'''
    n_bootstraps = 1000
    rng_seed = 42  # control reproducibility
    bootstrapped_scores = []

    rng = np.random.RandomState(rng_seed)
    for i in range(n_bootstraps):
        # bootstrap by sampling with replacement on the prediction indices
        indices = rng.randint(0, len(y), len(y))
        if len(np.unique(y[indices])) < 2: continue   # reject this sample
        score = skl_metrics.roc_auc_score(y[indices], yhat[indices])
        bootstrapped_scores.append(score)

    sorted_scores = np.array(bootstrapped_scores)
    sorted_scores.sort()

    confidence_lower = sorted_scores[int(0.025 * len(sorted_scores))]
    confidence_upper = sorted_scores[int(0.975 * len(sorted_scores))]
    return round(confidence_lower,3), round(confidence_upper,3)