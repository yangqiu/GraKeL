"""The weisfeiler lehman kernel :cite:`Shervashidze2011WeisfeilerLehmanGK`."""
import collections
import warnings

import numpy as np

from sklearn.exceptions import NotFittedError
from sklearn.utils.validation import check_is_fitted

from grakel.graph import Graph
from grakel.kernels import kernel

# Python 2/3 cross-compatibility import
from six import iteritems
from six import itervalues


class weisfeiler_lehman(kernel):
    """Compute the Weisfeiler Lehman Kernel.

     See :cite:`Shervashidze2011WeisfeilerLehmanGK`.

    Parameters
    ----------
    base_kernel : `grakel.kernels.kernel` or tuple
        If tuple it must consist of a valid kernel object and a
        dictionary of parameters. General parameters concerning
        normalization, concurrency, .. will be ignored, and the
        ones of given on `__init__` will be passed in case it is needed.

    niter : int, default=5
        The number of iterations.

    Attributes
    ----------
    X : dict
     Holds a dictionary of fitted subkernel modules for all levels.

    _nx : number
        Holds the number of inputs.

    _niter : int
        Holds the number, of iterations.

    _base_kernel : function
        A void function that initializes a base kernel object.

    _inv_labels : dict
        An inverse dictionary, used for relabeling on each iteration.

    """

    _graph_format = "dictionary"

    def __init__(self, **kargs):
        """Initialise a `weisfeiler_lehman` kernel."""
        base_params = self._valid_parameters.copy()
        self._valid_parameters |= {"base_kernel", "niter"}
        super(weisfeiler_lehman, self).__init__(**kargs)

        self._niter = kargs.get("niter", 5)
        if self._niter <= 0:
            raise ValueError('number of iterations must be greater than zero')
        self._niter += 1

        if "base_kernel" not in kargs:
            raise ValueError('User must provide a base kernel.')
        else:
            if type(kargs["base_kernel"]) is type and \
                    issubclass(kargs["base_kernel"], kernel):
                base_kernel = kargs["base_kernel"]
                params = dict()
            else:
                try:
                    base_kernel, params = kargs["base_kernel"]
                except Exception:
                    raise ValueError('Base kernel was not provided in the' +
                                     ' correct way. Check documentation.')

                if not (type(base_kernel) is type and
                        issubclass(base_kernel, kernel)):
                    raise ValueError('The first argument must be a valid ' +
                                     'grakel.kernel.kernel Object')
                if type(params) is not dict:
                    raise ValueError('If the second argument of base' +
                                     ' kernel exists, it must be a diction' +
                                     'ary between parameters names and values')
                params.pop("normalize", None)
                for p in base_params:
                        params.pop(p, None)

            params["normalize"] = False
            params["verbose"] = self._verbose
            params["executor"] = self._executor
            self._base_kernel = lambda *args: base_kernel(**params)

    def parse_input(self, X):
        """Parse input for weisfeiler lehman.

        Parameters
        ----------
        X : iterable
            For the input to pass the test, we must have:
            Each element must be an iterable with at most three features and at
            least one. The first that is obligatory is a valid graph structure
            (adjacency matrix or edge_dictionary) while the second is
            node_labels and the third edge_labels (that correspond to the given
            graph format). A valid input also consists of graph type objects.

        Returns
        -------
        base_kernel : object
        Returns base_kernel.

        """
        if self._method_calling not in [1, 2]:
            raise ValueError('method call must be called either from fit ' +
                             'or fit-transform')
        # Input validation and parsing
        if not isinstance(X, collections.Iterable):
            raise ValueError('input must be an iterable\n')
        else:
            nx = 0
            Gs_ed, L, distinct_values = dict(), dict(), set()
            for (idx, x) in enumerate(iter(X)):
                is_iter = isinstance(x, collections.Iterable)
                if is_iter:
                    x = list(x)
                if is_iter and len(x) in [0, 2, 3]:
                    if len(x) == 0:
                        warnings.warn('Ignoring empty element on index: '
                                      + str(idx))
                        continue
                    else:
                        x = Graph(x[0], x[1], {},
                                  graph_format=self._graph_format)
                elif type(x) is Graph:
                        x = Graph(x.get_edge_dictionary(),
                                  x.get_labels(purpose="dictionary"), {},
                                  graph_format=self._graph_format)
                else:
                    raise ValueError('each element of X must be either a ' +
                                     'graph object or a list with at least ' +
                                     'a graph like object and node labels ' +
                                     'dict \n')
                Gs_ed[nx] = x.get_edge_dictionary()
                L[nx] = x.get_labels(purpose="dictionary")
                distinct_values |= set(itervalues(L[nx]))
                nx += 1
            if nx == 0:
                raise ValueError('parsed input is empty')

        # Save the number of "fitted" graphs.
        self._nx = nx

        # get all the distinct values of current labels
        WL_labels_inverse = dict()

        # assign a number to each label
        label_count = 0
        for dv in sorted(list(distinct_values)):
            WL_labels_inverse[dv] = label_count
            label_count += 1

        # Initalize an inverse dictionary of labels for all iterations
        self._inv_labels = dict()
        self._inv_labels[0] = WL_labels_inverse

        new_graphs = list()
        for j in range(nx):
            new_labels = dict()
            for k in L[j].keys():
                new_labels[k] = WL_labels_inverse[L[j][k]]
            L[j] = new_labels
            # add new labels
            new_graphs.append([Gs_ed[j], new_labels])

        base_kernel = dict()
        base_kernel[0] = self._base_kernel()

        if self._method_calling == 1:
            base_kernel[0].fit(new_graphs)
        elif self._method_calling == 2:
            K = np.zeros(shape=(nx, nx))
            K += base_kernel[0].fit_transform(new_graphs)

        for i in range(1, self._niter):
            label_set, WL_labels_inverse, L_temp = set(), dict(), dict()
            for j in range(nx):
                # Find unique labels and sort
                # them for both graphs
                # Keep for each node the temporary
                L_temp[j] = dict()
                for v in Gs_ed[j].keys():
                    credential = str(L[j][v]) + "," + \
                        str(sorted([L[j][n] for n in Gs_ed[j][v].keys()]))
                    L_temp[j][v] = credential
                    label_set.add(credential)

            label_list = sorted(list(label_set))
            for dv in label_list:
                WL_labels_inverse[dv] = label_count
                label_count += 1

            # Recalculate labels
            new_graphs = list()
            for j in range(nx):
                new_labels = dict()
                for k in L_temp[j].keys():
                    new_labels[k] = WL_labels_inverse[L_temp[j][k]]
                L[j] = new_labels
                # relabel
                new_graphs.append([Gs_ed[j], new_labels])

            # calculate kernel
            base_kernel[i] = self._base_kernel()
            self._inv_labels[i] = WL_labels_inverse
            if self._method_calling == 1:
                base_kernel[i].fit(new_graphs)
            elif self._method_calling == 2:
                K += base_kernel[i].fit_transform(new_graphs)

        if self._method_calling == 1:
            return base_kernel
        elif self._method_calling == 2:
            return K, base_kernel

    def fit_transform(self, X):
        """Fit and transform, on the same dataset.

        Parameters
        ----------
        X : iterable
            Each element must be an iterable with at most three features and at
            least one. The first that is obligatory is a valid graph structure
            (adjacency matrix or edge_dictionary) while the second is
            node_labels and the third edge_labels (that fitting the given graph
            format). If None the kernel matrix is calculated upon fit data.
            The test samples.

        Returns
        -------
        K : numpy array, shape = [n_targets, n_input_graphs]
            corresponding to the kernel matrix, a calculation between
            all pairs of graphs between target an features

        """
        self._method_calling = 2
        if X is None:
            raise ValueError('transform input cannot be None')
        else:
            km, self.X = self.parse_input(X)

        self._X_diag = np.reshape(np.diagonal(km), (km.shape[0], 1))
        if self._normalize:
            return np.divide(km, np.sqrt(np.outer(self._X_diag, self._X_diag)))
        else:
            return km

    def transform(self, X):
        """Calculate the kernel matrix, between given and fitted dataset.

        Parameters
        ----------
        X : iterable
            Each element must be an iterable with at most three features and at
            least one. The first that is obligatory is a valid graph structure
            (adjacency matrix or edge_dictionary) while the second is
            node_labels and the third edge_labels (that fitting the given graph
            format). If None the kernel matrix is calculated upon fit data.
            The test samples.

        Returns
        -------
        K : numpy array, shape = [n_targets, n_input_graphs]
            corresponding to the kernel matrix, a calculation between
            all pairs of graphs between target an features

        """
        self._method_calling = 3
        # Check is fit had been called
        check_is_fitted(self, ['X', '_nx', '_inv_labels'])

        # Input validation and parsing
        if X is None:
            raise ValueError('transform input cannot be None')
        else:
            if not isinstance(X, collections.Iterable):
                raise ValueError('input must be an iterable\n')
            else:
                nx = 0
                distinct_values = set()
                Gs_ed, L = dict(), dict()
                for (i, x) in enumerate(iter(X)):
                    is_iter = isinstance(x, collections.Iterable)
                    if is_iter:
                        x = list(x)
                    if is_iter and len(x) in [0, 2, 3]:
                        if len(x) == 0:
                            warnings.warn('Ignoring empty element on index: '
                                          + str(i))
                            continue

                        elif len(x) in [2, 3]:
                            x = Graph(x[0], x[1], {}, self._graph_format)
                    elif type(x) is Graph:
                        x.desired_format("dictionary")
                    else:
                        raise ValueError('each element of X must have at ' +
                                         'least one and at most 3 elements\n')
                    Gs_ed[nx] = x.get_edge_dictionary()
                    L[nx] = x.get_labels(purpose="dictionary")

                    # Hold all the distinct values
                    distinct_values |= set(
                        v for v in itervalues(L[nx])
                        if v not in self._inv_labels[0])
                    nx += 1
                if nx == 0:
                    raise ValueError('parsed input is empty')

        WL_labels_inverse = dict()
        nl = len(self._inv_labels[0])
        WL_labels_inverse = {dv: idx for (idx, dv) in
                             enumerate(sorted(list(distinct_values)), nl)}

        # calculate the kernel matrix for the 0 iteration
        new_graphs = list()
        for j in range(nx):
            new_labels = dict()
            for (k, v) in iteritems(L[j]):
                if v in self._inv_labels[0]:
                    new_labels[k] = self._inv_labels[0][v]
                else:
                    new_labels[k] = WL_labels_inverse[v]
            L[j] = new_labels
            # produce the new graphs
            new_graphs.append([Gs_ed[j], new_labels])
        K = self.X[0].transform(new_graphs)

        for i in range(1, self._niter):
            new_graphs = list()
            L_temp, label_set = dict(), set()
            nl = len(self._inv_labels[i])
            for j in range(nx):
                # Find unique labels and sort them for both graphs
                # Keep for each node the temporary
                L_temp[j] = dict()
                for v in Gs_ed[j].keys():
                    credential = str(L[j][v]) + "," + \
                        str(sorted([L[j][n] for n in Gs_ed[j][v].keys()]))
                    L_temp[j][v] = credential
                    if credential not in self._inv_labels[i]:
                        label_set.add(credential)

            # Calculate the new label_set
            WL_labels_inverse = dict()
            if len(label_set) > 0:
                for dv in sorted(list(label_set)):
                    idx = len(WL_labels_inverse) + nl
                    WL_labels_inverse[dv] = idx

            # Recalculate labels
            new_graphs = list()
            for j in range(nx):
                new_labels = dict()
                for (k, v) in iteritems(L_temp[j]):
                    if v in self._inv_labels[i]:
                        new_labels[k] = self._inv_labels[i][v]
                    else:
                        new_labels[k] = WL_labels_inverse[v]
                L[j] = new_labels
                # Create the new graphs with the new labels.
                new_graphs.append([Gs_ed[j], new_labels])

            # Calculate the kernel marix
            K += self.X[i].transform(new_graphs)

        if self._normalize:
            X_diag, Y_diag = self.diagonal()
            return np.divide(K, np.sqrt(np.outer(Y_diag, X_diag)))
        else:
            return K

    def diagonal(self):
        """Calculate the kernel matrix diagonal for fitted data.

        A funtion called on transform on a seperate dataset to apply
        normalization on the exterior.

        Parameters
        ----------
        None.

        Returns
        -------
        X_diag : np.array
            The diagonal of the kernel matrix, of the fitted data.
            This consists of kernel calculation for each element with itself.

        Y_diag : np.array
            The diagonal of the kernel matrix, of the transformed data.
            This consists of kernel calculation for each element with itself.

        """
        # Check if fit had been called
        check_is_fitted(self, ['X'])
        try:
            check_is_fitted(self, ['_X_diag'])
            Y_diag = self.X[0].diagonal()[1]
            for i in range(1, self._niter):
                Y_diag += self.X[i].diagonal()[1]
        except NotFittedError:
            # Calculate diagonal of X
            X_diag, Y_diag = self.X[0].diagonal()
            X_diag.flags.writeable = True
            for i in range(1, self._niter):
                x, y = self.X[i].diagonal()
                X_diag += x
                Y_diag += y
            self._X_diag = X_diag

        return self._X_diag, Y_diag
