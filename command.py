from Commands.Keys import Button, Hat, Direction
from Commands.PythonCommandBase import ImageProcPythonCommand
from threading import Event
from time import perf_counter
from datetime import timedelta
import numpy as np
import os
import cv2
import traceback

from .mylib import image_process, SettingsManager
from .seed_searcher import SeedSearcherWrapper
from .lcg import GCLCG

class SettingKeys:
    SEARTH_METHOD = "SearchMethod"
    FULLDB_PATH = "FullDBPath"
    LIGHTDB_PATH = "LightDBPath"
    LANGUAGE = "Language"
    ADV_METHOD = "AdvancesMethod"
    ADV_VELOCITY = "AdvancesVelocity"
    SEARTH_MAX = "SearchMax"
    TIME_OFFSET = "TimeOffset"
    SHADOWS_POS = "ShadowPokemonPosition"
    FREQUENCY = "Frequency"
    
class SeedSearchAutomate(ImageProcPythonCommand):
    NAME = "Co_seed厳選自動化"

    def __init__(self, cam):
        super().__init__(cam)
        self.cur_dir = os.path.dirname(__file__)
        self.templates = os.path.join(self.cur_dir, "templates")
        self.event = Event()
        self.manager = SettingsManager()
        self.lang_dic = {
            "日本語":"JPN",
            "英語":"ENG",
            "ドイツ語":"GER",
            "フランス語":"FRA",
            "スペイン語":"SPA",
            "イタリア語":"ITA",
        }
        self.lang_list = list(self.lang_dic.keys())
        self.search_method_list = ["7回検索モード", "8回検索モード"]
        self.freq_list = ["60hz", "50hz"]
        self.shadow_pos_list =["1匹目", "2匹目", "3匹目", "4匹目", "5匹目", "6匹目"] 
        self.adv_method_list = ["ダークポケモン", "ダブルバトル", "消費しない"]
        self.is_first = True
        self.is_extension = hasattr(self, "print_t1") and callable(getattr(self, "print_t1"))
        self.push_amount = 0.1
        
    def do(self):
        self.command_init()
        # seed厳選開始
        while True:
            self.skip_opening()
            seed = self.seed_search()
            self.overwrite_ext_log(f"seed: {seed:08X}\n")
            result = self.target_seed_in_range(seed)
            if result is not None:
                target_seed, adv = result
                print("seedが見つかりました。")
                wait_time = self.calc_wait_time(adv)
                message = (
                    f"目標seed: {target_seed:08X}\n"
                    f"目標seedまでの消費数: {adv}\n"
                    f"待機時間: {timedelta(seconds=int(wait_time))}"
                )
                self._logger.info(message)
                self.write_ext_log(message)
                self.LINE_text(message)
                break
        self.wait_for_advance(wait_time)
        
    def command_init(self):
        try:
            self.target_seeds = self.read_target_seed_txt()
            if not self.target_seeds:
                raise Exception("TargetSeed.txtに目標seedが記述されていないため、マクロを終了します")
            self.manager.load_settings()
            self._setting = self.dialogue6widget(
                "設定",
                [
                    ["Radio", "検索方法" + " " * 80,  self.search_method_list, self.manager.get(SettingKeys.SEARTH_METHOD, self.search_method_list[0])],
                    ["Entry", "FullDBのパス", self.manager.get(SettingKeys.FULLDB_PATH, "C:\\")],
                    ["Entry", "LightDBのパス", self.manager.get(SettingKeys.LIGHTDB_PATH, "C:\\")],
                    ["Combo", "言語設定", self.lang_list, self.manager.get(SettingKeys.LANGUAGE, self.lang_list[0])],
                    ["Radio", "消費方法", self.adv_method_list, self.manager.get(SettingKeys.ADV_METHOD, self.adv_method_list[0])],
                    ["Entry", "消費速度(advances/s)", self.manager.get(SettingKeys.ADV_VELOCITY, "17146.6")],
                    ["Entry", "許容する消費数上限", self.manager.get(SettingKeys.SEARTH_MAX, "10000000")],
                    ["Spin", "待機時間の調整(差し引く秒数)", [str(i) for i in range(0, 501)], self.manager.get(SettingKeys.TIME_OFFSET, "0")],
                    ["Combo", "消費に使うダークポケモンの位置", self.shadow_pos_list, self.manager.get(SettingKeys.SHADOWS_POS, self.shadow_pos_list[0])],
                    ["Radio", "周波数(欧州版のみ)", self.freq_list, self.manager.get(SettingKeys.FREQUENCY, self.freq_list[0])],
                ],
            )
            self.valid_setting()
            self.manager.set(SettingKeys.SEARTH_METHOD, self._setting[0])
            self.manager.set(SettingKeys.FULLDB_PATH, self._setting[1])
            self.manager.set(SettingKeys.LIGHTDB_PATH, self._setting[2])
            self.manager.set(SettingKeys.LANGUAGE, self._setting[3])
            self.manager.set(SettingKeys.ADV_METHOD, self._setting[4])
            self.manager.set(SettingKeys.ADV_VELOCITY, self._setting[5])
            self.manager.set(SettingKeys.SEARTH_MAX, self._setting[6])
            self.manager.set(SettingKeys.TIME_OFFSET, self._setting[7])
            self.manager.set(SettingKeys.SHADOWS_POS, self._setting[8])
            self.manager.set(SettingKeys.FREQUENCY, self._setting[9])
            self.manager.save_settings()
            
        except Exception as e:
            print(f"{e}")
            traceback.print_exc()
            self.finish()
    
    def valid_setting(self):
        if not self._setting:
            raise Exception("")
        if self._setting[0] == "7回検索モード":
            self.searcher = SeedSearcherWrapper(self._setting[1], "full")
        elif self._setting[0] == "8回検索モード":
            self.searcher = SeedSearcherWrapper(self._setting[2], "light")
        
        if self._setting[3] not in self.lang_list:
            raise Exception("言語が正しく設定されていません")
        
        poke_files = [os.path.join(self.templates, "pokemon", f"{i}.png") for i in range(8)]
        player_files = [os.path.join(self.templates, "player", self.lang_dic[self._setting[3]], f"{i}.png") for i in range(3)]
        
        # 50hzにすると画面比率が微妙に変わるためリサイズする
        if self._setting[3] != "日本語" and self._setting[9] == "50hz":
            self.poke_mats = [
                cv2.resize(cv2.imread(file, cv2.IMREAD_GRAYSCALE), None, fx=1.0, fy=0.91, interpolation=cv2.INTER_LINEAR)
                for file in poke_files
            ]
            self.player_mats = [
                cv2.resize(cv2.imread(file, cv2.IMREAD_GRAYSCALE), None, fx=1.0, fy=0.91, interpolation=cv2.INTER_LINEAR)
                for file in player_files
            ]
            self.rep_interval = 0.2
            self.cancel_wait = 0.7
        else:
            self.poke_mats = [cv2.imread(file, cv2.IMREAD_GRAYSCALE) for file in poke_files]
            self.player_mats = [cv2.imread(file, cv2.IMREAD_GRAYSCALE) for file in player_files]
            self.rep_interval = 0.15
            self.cancel_wait = 0.6
        
        self.adv_velocity = float(self._setting[5])
        self.search_max = int(self._setting[6])
        self.time_offset = float(self._setting[7])
        if self._setting[8] not in self.shadow_pos_list:
            raise Exception("ダークポケモンの位置が正しく設定されていません")
        
    def skip_opening(self):
        self.hard_reset()
        if self._setting[3] != "日本語":
            self.wait(5)
            self.wait_freq_option()
            # 初回のみ周波数を選択する
            if self.is_first:
                direction = Hat.LEFT if self._setting[9] == "60hz" else Hat.RIGHT
                self.press(direction)
                self.press(Button.A)
                self.is_first = False
            self.press(Button.A, wait=3)
        else:
            self.wait(8)
            
        # ジニアスロゴ
        lower_blue = np.array([100, 100, 100])
        upper_blue = np.array([140, 255, 255]) 
        while image_process.calc_color_ratio(self.camera.readFrame(), lower_blue, upper_blue) < 0.5:
            self.checkIfAlive()
        
        if self.wait_load(10):
            self.wait_until_load_finishes()
        
        self.press_while_loading(Button.A)
        self.wait_until_load_finishes(0.2)
        self.press(Hat.RIGHT)
        self.press(Hat.BTM)
        self.press(Button.A, wait=2.5)
    
    def seed_search(self):
        keys = []
            
        for _ in range(self.searcher.specified_number_of_key):
            self.pressRep(Button.A, 3, interval=self.rep_interval, wait=0)
            keys.append(self.battlenow_detect())
            self.press(Button.B, wait=self.cancel_wait)
        seed_list = self.searcher.search(keys)
        
        while len(seed_list) > 1:
            keys = keys[1:]
            self.pressRep(Button.A, 3, interval=self.rep_interval, wait=0)
            keys.append(self.battlenow_detect())
            self.press(Button.B, wait=self.cancel_wait)
            seed_list = self.searcher.search(keys)
            
        if not seed_list:
            print("seedの検索に失敗しました")
            self.finish()
        return seed_list[0]

    def battlenow_detect(self, threshold=0.8):
        poke_scores = {}
        player_scores = {}
        
        start_time = perf_counter()
        
        while True:
            left, _ = image_process.split_img_vertical(self.camera.readFrame())
            img = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
            
            for idx, template_image in enumerate(self.poke_mats):
                result = cv2.matchTemplate(img, template_image, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val >= threshold:
                    poke_scores[idx] = max_val

            for idx, template_image in enumerate(self.player_mats):
                result = cv2.matchTemplate(img, template_image, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val >= threshold:
                    player_scores[idx] = max_val
                    
            if poke_scores and player_scores:
                poke_idx = max(poke_scores, key=poke_scores.get)
                player_idx = max(player_scores, key=player_scores.get)
                # self._logger.debug(f"Pokemon: {poke_idx}, score: {poke_scores[poke_idx]:.4f}")
                # self._logger.debug(f"Player: {player_idx}, score: {player_scores[player_idx]:.4f}")
                return player_idx, poke_idx

            if perf_counter() - start_time > 5:
                print("一定時間画像を認識できなかったためマクロを終了します")
                self.finish()
            
            self.checkIfAlive()
    
    def wait_for_advance(self, wait_time):
        if self._setting[4] == self.adv_method_list[0]:
            self.advance_by_shadows(wait_time)
        elif self._setting[4] == self.adv_method_list[1]:
            self.advance_by_battle(wait_time)
        else:
            print("設定により消費は行われませんでした。")
    
    def advance_by_battle(self, wait_time: float):
        force_wait_time = 45 # バトル開始から降参可能になるまでの大体の時間
        wait_time -= force_wait_time
        if wait_time < 1:
            print("待機時間が1秒に満たなかったため、消費は行われませんでした。")
            return
        self.press(Hat.RIGHT)
        self.press_while_loading(Button.A)
        self.wait_until_load_finishes(12)
        self.press(Hat.LEFT)
        self.press(Hat.TOP)
        self.press(Hat.BTM)
        self.press(Hat.RIGHT, wait=0.6)
        self.press(Button.A)
        if self.wait_load(5):
            self.wait_until_load_finishes()
        print("-- 消費中です -- ")
        self.cancellation_wait(force_wait_time)
        self.press(Hat.RIGHT, wait=0.15)
        self.press(Button.A, wait=0.15)
        self.press(Hat.RIGHT, wait=0.15)
        self.press(Button.A, wait=0.15)
        self.press(Hat.RIGHT, wait=0.15)
        self.press(Button.A, wait=0.15)
        self.press(Hat.RIGHT, wait=0.15)
        self.cancellation_wait(wait_time)
        self.press(Button.A)
        if self.wait_load(5):
            self.wait_until_load_finishes()
        self.press_while_loading(Button.B)
        print("-- 消費が終了しました -- ")
        
    def advance_by_shadows(self, wait_time):
        # 続きから
        self.press(Button.B, wait=2.5)
        self.press(Button.A, wait=0.5)
        self.press(Hat.TOP)
        self.press(Button.A)
        if self.wait_load(5):
            self.wait_until_load_finishes()
        # 手持ち開く -> 大量消費
        self.open_party_menu()
        if wait_time < 1:
            print("待機時間が1秒に満たなかったため、消費は行われませんでした。")
            return
        for _ in range(self.shadow_pos_list.index(self._setting[8])):
            self.press(Hat.BTM)
        print("-- 消費中です -- ")
        self.pressRep(Button.A, 2)
        if self.wait_load(5):
            self.wait_until_load_finishes()
        self.cancellation_wait(wait_time)
        self.press(Button.B)
        print("-- 消費が終了しました -- ")

    def wait_load(self, timeout):
        start = perf_counter()
        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 50])
        
        while True:
            if image_process.calc_color_ratio(self.camera.readFrame(), lower_black, upper_black) >= 0.8:
                return True
            elapsed_time = perf_counter() - start
            if elapsed_time > timeout:
                return False
            self.checkIfAlive()
            self.wait(0.2)
            
    def is_contain_template_wait(self, template, threshold, wait):
        start = perf_counter()
        while True:
            img = cv2.cvtColor(self.camera.readFrame(), cv2.COLOR_BGR2GRAY)
            res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > threshold:
                return True
            if perf_counter() - start > wait:
                return False
            # self.wait(0.1)

    def wait_until_load_finishes(self, interval=0, threshold=0.9):
        """
        暗転が終わる（ロードが終わる）まで待つ
        """
        
        lower = np.array([0, 0, 0])
        upper = np.array([180, 255, 50])
        while image_process.calc_color_ratio(self.camera.readFrame(), lower, upper) > threshold:
            self.checkIfAlive()
        self.wait(interval)

    def wait_freq_option(self, lower=np.array([0, 0, 200]), upper=np.array([180, 30, 255]), timeout=5):
        start_time = perf_counter()
        while True:
            _, lower_img = image_process.split_img_horizonal(self.camera.readFrame())
            hsv_img = cv2.cvtColor(lower_img, cv2.COLOR_BGR2HSV) 
            if np.any(cv2.inRange(hsv_img, lower, upper) > 0):
                return
            if perf_counter() - start_time > timeout:
                return
            self.wait(0.1)

    def press_while_loading(self, button, duration=0.1, wait=0.1, threshold=0.9):
        """
        暗転するまでボタンを押す
        """
        
        lower = np.array([0, 0, 0])
        upper = np.array([180, 255, 50])
        while not image_process.calc_color_ratio(self.camera.readFrame(), lower, upper) > threshold:
            self.press(button, duration, wait)

    def write_ext_log(self, text):
        if self.is_extension:
            self.print_t(text)
        else:
            print(text)
    
    def overwrite_ext_log(self, text):
        if self.is_extension:
            self.print_tb("w", text)
        else:
            print(text)
    
    def read_target_seed_txt(self):
        seed_list = []
        file_path = os.path.join(self.cur_dir, "TargetSeed.txt")
        
        if not os.path.exists(file_path):
            with open(file_path, "w") as file:
                pass
            
        with open(file_path, "r") as file:
            for line in file:
                hex_str = line.strip()
                try:
                    seed = int(hex_str, 16)
                    seed_list.append(seed)
                except ValueError:
                    pass
        return seed_list

    def open_party_menu(self):
        self.press(Button.X, wait=0.5)
        self.press(Button.A, wait=1.8)
    
    def target_seed_in_range(self, current_seed):
        for target_seed in self.target_seeds:
            adv = GCLCG.get_index(target_seed, current_seed)
            self._logger.debug(f"TargetSeed: {target_seed:08X} Advance: {adv}")
            if adv <= self.search_max:
                return (target_seed, adv)
        return None
    
    def calc_wait_time(self, adv):
        return (adv / self.adv_velocity) - self.time_offset

    def hard_reset(self, max_count=5):
        count = 0
        self.press(Button.HOME, duration=self.push_amount)
        while count < max_count:
            if not self.wait_load(3):
                self.push_amount += 0.1
                self.press(Button.HOME, duration=self.push_amount)
            else:
                break
            count += 1
            if count == max_count - 1:
                print("リセットに失敗したためマクロを終了します")
                self.finish()
    
    def cancellation_wait(self, wait_time: float):
        if wait_time < 3:
            start_time = perf_counter()
            while (perf_counter() - start_time) < wait_time:
                self.checkIfAlive()
        else:
            start_time = perf_counter()
            self.event.wait(wait_time - 3)
            while (perf_counter() - start_time) < wait_time:
                self.checkIfAlive()
    
    def end(self, ser):
        self.event.set()
        super().end(ser)