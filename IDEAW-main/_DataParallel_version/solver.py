""" Training implementation for IDEAW
"""

""" Train on multiple GPUs
"""

import torch
import torch.nn
import yaml

from data.dataset import AWdataset, get_data_loader, infinite_iter
from models.ideaw import IDEAW
from metrics import calc_acc, signal_noise_ratio


class Solver(object):
    def __init__(self, config_data_path, config_model_path, args):
        self.config_data_path = config_data_path
        self.config_model_path = config_model_path
        self.args = args  # training config inside
        self.device = self.args.device

        with open(self.config_data_path) as f:
            self.config_data = yaml.load(f, Loader=yaml.FullLoader)
        with open(self.config_model_path) as f:
            self.config_model = yaml.load(f, Loader=yaml.FullLoader)
        with open(self.args.train_config) as f:
            self.config_t = yaml.load(f, Loader=yaml.FullLoader)

        self.get_inf_train_iter()  # prepare data
        self.build_model()  # prepare model
        self.build_optims()  # prepare optimizers
        self.loss_criterion()  # prepare criterions

        if self.args.load_model:
            self.load_model()

    # prepare data, called in Solver.init
    def get_inf_train_iter(self):
        dataset_dir = self.args.pickle_path
        self.dataset = AWdataset(dataset_dir)
        self.batch_size = self.config_t["train"]["batch_size"]
        self.num_workers = self.config_t["train"]["num_workers"]
        self.shift = False
        self.train_iter = infinite_iter(
            get_data_loader(
                dataset=self.dataset,
                batch_size=self.batch_size,
                num_workers=self.num_workers,
            )
        )
        print("[IDEAW]infinite dataloader built")
        return

    # load model/data to cuda
    def cc_dp(self, net):
        net = torch.nn.DataParallel(net, device_ids=[0, 1, 2, 3])
        device = torch.device("cuda:0")
        return net.to(device)

    def cc(self, data):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return data.to(device)

    # called in Solver.init
    def build_model(self):
        self.model = self.cc(IDEAW(self.config_model_path, self.device))
        print("[IDEAW]model built")
        print(
            "[IDEAW]total parameter count: {}".format(
                sum(x.numel() for x in self.model.parameters())
            )
        )

    # called in Solver.init
    def build_optims(self):
        param_hinet1 = list(
            filter(lambda p: p.requires_grad, self.model.module.hinet_1.parameters())
        )
        param_hinet2 = list(
            filter(lambda p: p.requires_grad, self.model.module.hinet_2.parameters())
        )
        param_discr = list(
            filter(
                lambda p: p.requires_grad, self.model.module.discriminator.parameters()
            )
        )
        param_att = list(
            filter(
                lambda p: p.requires_grad, self.model.module.attack_layer.parameters()
            )
        )
        param_balance = list(
            filter(
                lambda p: p.requires_grad, self.model.module.balance_block.parameters()
            )
        )

        lr1 = eval(self.config_t["train"]["lr1"])
        lr2 = eval(self.config_t["train"]["lr2"])
        beta1 = self.config_t["train"]["beta1"]
        beta2 = self.config_t["train"]["beta2"]
        eps = eval(self.config_t["train"]["eps"])
        weight_decay = eval(self.config_t["train"]["weight_decay"])

        self.optim_I = torch.optim.Adam(
            param_hinet1 + param_hinet2,
            lr=lr1,
            betas=(beta1, beta2),
            eps=eps,
            weight_decay=weight_decay,
        )
        self.optim_II = torch.optim.Adam(
            param_att + param_balance,
            lr=lr2,
            betas=(beta1, beta2),
            eps=eps,
            weight_decay=weight_decay,
        )
        self.optim_III = torch.optim.Adam(
            param_discr,
            lr=lr1,
            betas=(beta1, beta2),
            eps=eps,
            weight_decay=weight_decay,
        )
        self.weight_scheduler1 = torch.optim.lr_scheduler.StepLR(
            self.optim_I,
            self.config_t["train"]["weight_step"],
            gamma=self.config_t["train"]["gamma"],
        )
        self.weight_scheduler2 = torch.optim.lr_scheduler.StepLR(
            self.optim_II,
            self.config_t["train"]["weight_step"],
            gamma=self.config_t["train"]["gamma"],
        )
        self.weight_scheduler1 = torch.optim.lr_scheduler.StepLR(
            self.optim_III,
            self.config_t["train"]["weight_step"],
            gamma=self.config_t["train"]["gamma"],
        )
        print("[IDEAW]optimizers built")

    # autosave, called in training
    def save_model(self, robustness):
        if robustness:
            torch.save(
                self.model.state_dict(),
                f"{self.args.store_model_path}stage_II/ideaw.ckpt",
            )
            torch.save(
                self.optim_I.state_dict(),
                f"{self.args.store_model_path}stage_II/optim1.opt",
            )
            torch.save(
                self.optim_II.state_dict(),
                f"{self.args.store_model_path}stage_II/optim2.opt",
            )
            torch.save(
                self.optim_III.state_dict(),
                f"{self.args.store_model_path}stage_II/optim3.opt",
            )
        else:
            torch.save(
                self.model.state_dict(),
                f"{self.args.store_model_path}stage_I/ideaw.ckpt",
            )
            torch.save(
                self.optim_I.state_dict(),
                f"{self.args.store_model_path}stage_I/optim1.opt",
            )
            torch.save(
                self.optim_II.state_dict(),
                f"{self.args.store_model_path}stage_I/optim2.opt",
            )
            torch.save(
                self.optim_III.state_dict(),
                f"{self.args.store_model_path}stage_I/optim3.opt",
            )

    # load trained model
    def load_model(self):
        print(f"[IDEAW]load model from {self.args.load_model_path}")
        self.model.load_state_dict(torch.load(f"{self.args.load_model_path}ideaw.ckpt"))
        self.optim_I.load_state_dict(
            torch.load(f"{self.args.load_model_path}optim1.opt")
        )
        self.optim_II.load_state_dict(
            torch.load(f"{self.args.load_model_path}optim2.opt")
        )
        self.optim_III.load_state_dict(
            torch.load(f"{self.args.load_model_path}optim3.opt")
        )
        return

    # loss criterion
    def loss_criterion(self):
        self.criterion_percept = torch.nn.MSELoss()
        self.criterion_integ = torch.nn.MSELoss()
        self.criterion_discr = torch.nn.BCELoss()

    # training
    def train(self, n_iterations):
        print("[IDEAW]starting training...")
        percept_loss_history = []
        integ_loss_history = []
        discr_loss_history = []
        ident_loss_history = []
        for iter in range(n_iterations):
            # get data for current iteration
            host_audio = next(self.train_iter).to(torch.float32)
            msg_len = self.config_model["IDEAW"]["num_bit"]
            lcode_len = self.config_model["IDEAW"]["num_lc_bit"]
            watermark_msg = torch.randint(
                0, 2, (self.batch_size, msg_len), dtype=torch.float32
            )
            locate_code = torch.randint(
                0, 2, (self.batch_size, lcode_len), dtype=torch.float32
            )
            orig_label = torch.ones((self.batch_size, 1))
            wmd_label = torch.zeros((self.batch_size, 1))

            ## load to cuda
            host_audio = self.cc(host_audio)
            watermark_msg = self.cc(watermark_msg)
            locate_code = self.cc(locate_code)
            orig_label = self.cc(orig_label)
            wmd_label = self.cc(wmd_label)

            # forward
            ## stage I training
            if iter < n_iterations / 2:
                robustness = False
            ## stage II training (robustness training)
            else:
                robustness = True
            (
                _,
                _,
                audio_wmd2,
                audio_wmd2_stft,
                msg_extr1,
                msg_extr2,
                lcode_extr,
                orig_output,
                wmd_output,
            ) = self.model(
                host_audio, watermark_msg, locate_code, robustness, self.shift
            )

            # loss
            ## percept. loss
            host_audio_stft = self.model.module.stft(host_audio)
            percept_loss = self.criterion_percept(host_audio_stft, audio_wmd2_stft)
            percept_loss_history.append(percept_loss.item())
            ## integrity loss
            integ_loss_1 = self.criterion_integ(watermark_msg, msg_extr1)
            integ_loss_2 = self.criterion_integ(watermark_msg, msg_extr2)
            integ_loss_3 = self.criterion_integ(locate_code, lcode_extr)
            integ_loss = integ_loss_1 + integ_loss_2 + integ_loss_3
            integ_loss_history.append(integ_loss.item())
            ## discriminate loss
            discr_loss_orig = self.criterion_discr(orig_output, orig_label)
            discr_loss_wmd = self.criterion_discr(wmd_output, wmd_label)
            discr_loss = discr_loss_orig + discr_loss_wmd
            discr_loss_history.append(discr_loss.item())
            ## identify loss
            ident_loss = -torch.sum(torch.log(1 - wmd_output))
            ident_loss_history.append(ident_loss)
            ## total loss
            discr_frozen = True
            if iter % 2 == 1:
                discr_frozen = False
                total_loss = (
                    self.lambda_1 * integ_loss
                    + self.lambda_2 * percept_loss
                    + self.lambda_3 * discr_loss
                )
            else:
                discr_frozen = True
                total_loss = (
                    self.lambda_1 * integ_loss
                    + self.lambda_2 * percept_loss
                    + self.lambda_3 * ident_loss
                )

            # metric
            acc_msg = calc_acc(msg_extr2, watermark_msg, 0.5)
            acc_lcode = calc_acc(lcode_extr, locate_code, 0.5)
            snr = signal_noise_ratio(host_audio, audio_wmd2)

            # backward
            total_loss.backward()

            if eval(self.config_t["train"]["optim1_step"]):
                self.optim_I.step()
                self.weight_scheduler1.step()
            if eval(self.config_t["train"]["optim2_step"]):
                self.optim_II.step()
                self.weight_scheduler2.step()
            if discr_frozen == False:
                self.optim_III.step()
                self.weight_scheduler3.step()
            self.optim_I.zero_grad()
            self.optim_II.zero_grad()
            self.optim_III.zero_grad()

            # logging
            print(
                f"[IDEAW]:[{iter+1}/{n_iterations}]",
                f"Robustness={robustness}",
                f"shift={self.shift}",
                f"loss_percept={percept_loss.item():.6f}",
                f"loss_integ={integ_loss.item():6f}",
                f"loss_discr={discr_loss.item():6f}",
                f"loss_ident={ident_loss.item():6f}",
                f"SNR={snr:4f}",
                f"acc_msg={acc_msg:4f}",
                f"acc_lcode={acc_lcode:4f}",
                end="\r",
            )

            # summary
            if (iter + 1) % self.args.summary_steps == 0 or iter + 1 == n_iterations:
                print()

            # autosave
            if (iter + 1) % self.args.save_steps == 0 or iter + 1 == n_iterations:
                self.save_model(robustness)

        return
