"""Utils for parsing PBA augmentation schedules."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import ast
import collections
import tensorflow as tf


PbtUpdate = collections.namedtuple('PbtUpdate', [
    'target_trial_name', 'clone_trial_name', 'target_trial_epochs',
    'clone_trial_epochs', 'old_config', 'new_config'
])


def parse_log(file_path, epochs):
    """Parses augmentation policy schedule from log file.

  Args:
    file_path: Path to policy generated by running search.py.
    epochs: The number of epochs search was run for.

  Returns:
    A list containing the parsed policy of the form: [start epoch, start_epoch_clone, policy], where each element is a tuple of (num_epochs, policy list).
  """
    raw_policy_file = open(file_path, "r").readlines()
    raw_policy = []
    for line in raw_policy_file:
        try:
            raw_policy_line = json.loads(line)
        except:
            raw_policy_line = ast.literal_eval(line)
        raw_policy.append(raw_policy_line)

    # Depreciated use case has policy as list instead of dict config.
    for r in raw_policy:
        for i in [4, 5]:
            if isinstance(r[i], list):
                r[i] = {"hp_policy": r[i]}
    raw_policy = [PbtUpdate(*r) for r in raw_policy]
    policy = []

    # Sometimes files have extra lines in the beginning.
    to_truncate = None
    for i in range(len(raw_policy) - 1):
        if raw_policy[i][0] != raw_policy[i + 1][1]:
            to_truncate = i
    if to_truncate is not None:
        raw_policy = raw_policy[to_truncate + 1:]

    # Initial policy for trial_to_clone_epochs.
    policy.append([raw_policy[0][3], raw_policy[0][4]["hp_policy"]])

    current = raw_policy[0][3]
    for i in range(len(raw_policy) - 1):
        # End at next line's trial epoch, start from this clone epoch.
        this_iter = raw_policy[i + 1][3] - raw_policy[i][3]
        assert this_iter >= 0, (i, raw_policy[i + 1][3], raw_policy[i][3])
        assert raw_policy[i][0] == raw_policy[i + 1][1], (i, raw_policy[i][0],
                                                          raw_policy[i + 1][1])
        policy.append([this_iter, raw_policy[i][5]["hp_policy"]])
        current += this_iter

    # Last cloned trial policy is run for (end - clone iter of last logged line)
    policy.append([epochs - raw_policy[-1][3], raw_policy[-1][5]["hp_policy"]])
    current += epochs - raw_policy[-1][3]
    assert epochs == sum([p[0] for p in policy])
    return policy


def parse_log_schedule(file_path, epochs, multiplier=1):
    """Parses policy schedule from log file.

  Args:
    file_path: Path to policy generated by running search.py.
    epochs: The number of epochs search was run for.
    multiplier: Multiplier on number of epochs for each policy in the schedule..

  Returns:
    List of length epochs, where index i contains the policy to use at epoch i.
  """
    policy = parse_log(file_path, epochs)
    schedule = []
    count = 0
    for num_iters, pol in policy:
        tf.logging.debug("iters {} by multiplier {} result: {}".format(
            num_iters, multiplier, num_iters * multiplier))
        for _ in range(int(num_iters * multiplier)):
            schedule.append(pol)
            count += 1
    if int(epochs * multiplier) - count > 0:
        tf.logging.info("len: {}, remaining: {}".format(
            count, epochs * multiplier))
    for _ in range(int(epochs * multiplier) - count):
        schedule.append(policy[-1][1])
    tf.logging.info("final len {}".format(len(schedule)))
    return schedule


if __name__ == "__main__":
    import glob
    import json
    import os

    exp_name = 'mnli_mm_search_all_augm_3000'
    task_name = 'mnli_mm'
    n_models = 16

    folder = os.path.join('results',exp_name)
    measure = {'mnli_mm': 'test_acc', 'sst-2': 'test_acc'}

    # --- parse all results files and look at test_acc on 100 samples at the end of the search
    test_measure = []
    for model in range(n_models):
        results = []
        with open(glob.glob(os.path.join(folder, f'RayModel_{model}_*', 'result.json'))[0]) as file:
            for jsonObject in file:
                results.append(json.loads(jsonObject))
            test_measure.append(results[-1][measure[task_name]])

    # select the model that performed the best on the 100 test samples at the end of the search
    best_model = test_measure.index(max(test_measure))



    # --- parse policy file to get schedule
    with open(os.path.join(folder, f'pbt_policy_{str(best_model).zfill(5)}.txt')) as policy_file:
        first = True
        for line in policy_file:
            parsed_params = []
            params = json.loads(line)
            parsed_params.append(params[0])
            parsed_params.append(params[1])
            parsed_params.append(params[2])
            parsed_params.append(params[3])
            parsed_params.append(params[4]['hp_policy'])
            parsed_params.append(params[5]['hp_policy'])
            if first == True:
                with open(os.path.join('schedules',f'{exp_name}.txt'), 'w') as the_file:
                    the_file.write(str(parsed_params)+'\n')
                first = False
            else:
                with open(os.path.join('schedules',f'{exp_name}.txt'), 'a') as the_file:
                    the_file.write(str(parsed_params)+'\n')
