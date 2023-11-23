import re
import requests
import json
from struct import *
from enum import Enum

TEMP_NA = 960


class PitbossApi:
    _debug = False

    _state = {
        'id': "",
        'PowerOn': False,
        'FanOn': False,
        'IgniterOn': False,
        'MotorOn': False,
        'LightOn': False,
        'Priming': False,
        'P1SetTemp': 0,
        'P1ActTemp': 0,
        'P2ActTemp': 0,
        'P3ActTemp': 0,
        'P4ActTemp': 0,
        'GrillSetTemp': 0,
        'GrillActTemp': 0,
        'IsFarenheit': False,
        'Errors': {
            'Err1': False,
            'Err2': False,
            'Err3': False,
            'HighTempErr': False,
            'FanErr': False,
            'HotErr': False,
            'MotorErr': False,
            'NoPellets': False,
            'ErL': False,
        },
        'Error': False,
        'ErrorStr': "",
        'Recipe': {
            'RecipeStep': 0,
            'TimeH': 0,
            'TimeM': 0,
            'TimeS': 0
        }
    }

    class Command(Enum):
        SetPowerState = "01"
        SetTemperature = "05"
        SetConnectedStatus = "24"
        GetStatus11 = "0B"
        GetStatus12 = "0C"
        ControlPrimeMotor = "08"
        ControlLight = "02"
        SetTempFC = "09"

    class Temp(Enum):
        Grill = "01"
        Probe1 = "02"

    def temp2hex(val: int):
        temp = "{:3d}".format(val)
        temp = re.sub(r"(\d)(\d)(\d)", r"0\g<1>0\g<2>0\g<3>", temp)
        return temp

    def __init__(self, host) -> None:
        self._host = host
        self._url = f"http://{self._host}/rpc"

    def hex2temp(val):
        temp = val[0]*100+val[1]*10+val[2]
        temp = 0 if (temp == TEMP_NA) else temp
        return temp

    def SendCommand(self, cmd: Command, val):
        Header = "FE"
        Postamble = "FF"
        cmd = Header + cmd.value + val + Postamble

        resp = requests.post(
            self._url+"/PB.SendMCUCommand", json={"command": cmd})
        print(resp.text) if self._debug else ()

    def SetGrillTemp(self, temp):
        self.SendCommand(PitbossApi.Command.SetTemperature,
                         PitbossApi.Temp.Grill.value + PitbossApi.temp2hex(int(temp)))

    def SetProbe1Temp(self, temp):
        self.SendCommand(PitbossApi.Command.SetTemperature,
                         PitbossApi.Temp.Probe1.value + PitbossApi.temp2hex(int(temp)))

    def SetPrimeState(self, state):
        self.SendCommand(PitbossApi.Command.ControlPrimeMotor,
                         "01" if state == True else "00")

    def SetMCUUpdateFrequency(self, freq):
        resp = requests.post(
            self._url+"/PB.SetMCU_UpdateFrequency", json={"frequency": freq})
        print(resp.text) if self._debug else ()

    def SetPowerState(self, val: bool):
        self.SendCommand(PitbossApi.Command.SetPowerState,
                         "01" if val == True else "02")

    def UpdateUniqueID(self):
        resp = requests.get(self._url+"/Sys.GetInfo")

        if resp.status_code != 200:
            return "ERROR"
        # TODO: improve the validation here

        self._state['id'] = resp.json()["id"]

    def GetUniqueID(self):
        return self._state['id']

    def UpdateState(self):
        self.UpdateUniqueID()

        resp = requests.get(self._url+"/PB.GetState").json()
        print(json.dumps(resp)) if self._debug else ()

        sc12 = bytes.fromhex(resp['sc_12'])
        sc11 = bytes.fromhex(resp['sc_11'])

        if sc12 == b'' or sc11 == b'':
            print("Warning: could not update state")
            print(resp)
            return

        P1SetTemp,              \
            P1ActTemp,              \
            P2ActTemp,              \
            P3ActTemp,              \
            P4ActTemp,              \
            SmokerActTemp,          \
            GrillSetTemp,           \
            GrillActTemp,           \
            self._state['IsFarenheit']   \
            = unpack("xx3s3s3s3s3s3s3s3s?x", sc12)

        P1SetTemp,              \
            P1ActTemp,              \
            P2ActTemp,              \
            P3ActTemp,              \
            P4ActTemp,              \
            SmokerActTemp,          \
            MiscTemp,               \
            MiscTempSel,            \
            ModuleIsOn,             \
            self._state['Errors']['Err1'],         \
            self._state['Errors']['Err2'],         \
            self._state['Errors']['Err3'],         \
            self._state['Errors']['HighTempErr'],  \
            self._state['Errors']['FanErr'],       \
            self._state['Errors']['HotErr'],       \
            self._state['Errors']['MotorErr'],     \
            self._state['Errors']['NoPellets'],    \
            self._state['Errors']['ErL'],          \
            self._state['FanOn'],        \
            self._state['IgniterOn'],    \
            self._state['MotorOn'],      \
            self._state['LightOn'],      \
            self._state['Priming'],      \
            self._state['IsFarenheit'],  \
            self._state['Recipe']['RecipeStep'],   \
            self._state['Recipe']['TimeH'],        \
            self._state['Recipe']['TimeM'],        \
            self._state['Recipe']['TimeS']         \
            = unpack("xx3s3s3s3s3s3s3sBB???????????????BBBBx", sc11)

        self._state['P1SetTemp'] = PitbossApi.hex2temp(P1SetTemp)
        self._state['P1ActTemp'] = PitbossApi.hex2temp(P1ActTemp)
        self._state['P2ActTemp'] = PitbossApi.hex2temp(P2ActTemp)
        self._state['P3ActTemp'] = PitbossApi.hex2temp(P3ActTemp)
        self._state['P4ActTemp'] = PitbossApi.hex2temp(P4ActTemp)
        self._state['SmokerActTemp'] = PitbossApi.hex2temp(SmokerActTemp)
        self._state['GrillSetTemp'] = PitbossApi.hex2temp(GrillSetTemp)
        self._state['GrillActTemp'] = PitbossApi.hex2temp(GrillActTemp)

        self._state['PowerOn'] = True if ModuleIsOn == 1 else False

        error = False
        err_str = ""
        for e in self._state['Errors']:
            if self._state['Errors'][e] == True:
                error = True
                err_str += " " + e
        self._state['Error'] = error
        self._state['ErrorStr'] = err_str

    def GetStateValue(self, key):
        return self._state[key]
