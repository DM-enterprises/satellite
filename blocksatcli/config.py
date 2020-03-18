"""User setup configuration"""
import os, json, logging
from argparse import ArgumentDefaultsHelpFormatter
from pprint import pprint, pformat
from . import util, defs, instructions
import textwrap
from decimal import Decimal, getcontext


def _cfg_satellite():
    """Configure satellite covering the user"""

    util._print_header("Satellite")

    help_msg = "Not sure? Check the coverage map at:\n" \
               "https://blockstream.com/satellite/#satellite_network-coverage"

    question = "Please, inform which satellite below covers your location:"
    sat = util._ask_multiple_choice(defs.satellites,
                                    question,
                                    "Satellite",
                                    lambda sat : '{} ({})'.format(sat['name'],
                                                                  sat['alias']),
                                    help_msg)
    return sat


def _cfg_rx_setup():
    """Configure Rx setup - which receiver user is using """

    util._print_header("Receiver Setup")

    question = "Please, inform your DVB-S2 receiver setup from the list below:"
    modem = util._ask_multiple_choice(defs.modems,
                                      question,
                                      "Setup",
                                      lambda x : '{} receiver, using {} modem'.format(
                                          x['type'],
                                          (x['vendor'] + " " +
                                           x['model']).strip()))

    if (modem['type'] == defs.standalone_setup_type):
        try:
            devices = os.listdir('/sys/class/net/')
        except FileNotFoundError:
            devices = None
            pass

        question = "Which network interface is connected to the {}?".format(
            modem['model'])
        if (devices is not None):
            netdev = util._ask_multiple_choice(devices,
                                               question,
                                               "Interface",
                                               lambda x : '{}'.format(x))
        else:
            netdev = input(question + " ")

        modem['netdev'] = netdev.strip()

    return modem


def _cfg_custom_lnb(sat):
    """Configure custom LNB based on user-entered specs

    Args:
        sat : user's satellite info

    """

    print("\nPlease inform the specifications of your LNB:")

    print("Frequency band:")
    bands = ["C", "Ku"]
    for i_band, band in enumerate(bands):
        print("[%2u] %s" %(i_band, band))

    resp = input("Enter number: ") or None

    try:
        custom_lnb_band = bands[int(resp)]
    except ValueError:
        raise ValueError("Please choose a number")

    if (sat['band'].lower() != custom_lnb_band.lower()):
        logging.error(
            "You must use a %s band LNB in order to receive from %s" %(
                sat['band'], sat['name']))
        exit(1)


    if (custom_lnb_band == "Ku"):
        custom_lnb_universal = util._ask_yes_or_no("Is it a Universal Ku band LNB?")

        if (custom_lnb_universal):
            print(textwrap.fill(
                "A Universal Ku band LNB has two LO (local oscillator) " + \
                " frequencies. Typically the two frequencies are 9750 MHz " +
                "and 10600 MHz."))
            if (util._ask_yes_or_no("Does your LNB have LO frequencies 9750 MHz and 10600 MHz?")):
                custom_lnb_lo_freq = [9750.0, 10600]
            else:
                custom_lnb_lo_freq = []
                while (len(custom_lnb_lo_freq) != 2):
                    try:
                        resp = input("Inform the two LO frequencies in MHz, "
                                     "separated by comma: ")
                        custom_lnb_lo_freq = [float(x) for x in resp.split(",")]
                    except ValueError:
                        continue

        else:
            # Non-universal Ku-band LNB
            try:
                custom_lnb_lo_freq = float(input("LNB LO frequency in MHz: "))
            except ValueError:
                raise ValueError("Please enter a number")
    else:
        # C-band LNB
        custom_lnb_universal = False
        try:
            custom_lnb_lo_freq = float(input("LNB LO frequency in MHz: "))
        except ValueError:
            raise ValueError("Please enter a number")


    # Polarization
    question = "Choose the LNB polarization:"
    options = [
        {
            'id' : "Dual",
            'text' : "Dual polarization (horizontal and vertical)"
        },
        {
            'id' : "H",
            'text' : "Horizontal"
        },
        {
            'id' : "V",
            'text' : "Vertical"
        }]
    pol = util._ask_multiple_choice(options, question,
                                    "Polarization",
                                    lambda x : '{}'.format(x['text']))

    return {
        'vendor'    : "",
        'model'     : "",
        "lo_freq"   : custom_lnb_lo_freq,
        'universal' : custom_lnb_universal,
        'band'      : custom_lnb_band,
        'pol'       : pol['id']
    }


def _cfg_lnb(sat, setup):
    """Configure LNB - either from preset or from custom specs

    Args:
        sat   : user's satellite info
        setup : user's rx setup info

    """

    util._print_header("LNB")

    print("Commonly used LNBs:")

    for i_lnb, lnb in enumerate(defs.lnbs):
        if (lnb['universal']):
            print("[%2u] %s %s (Universal Ku band LNBF)" %(i_lnb,
                                                           lnb['vendor'],
                                                           lnb['model']))
        else:
            print("[%2u] %s %s" %(i_lnb, lnb['vendor'], lnb['model']))

    print()
    if (util._ask_yes_or_no("Are you using one of the above LNBs?")):
        resp = None
        while (not isinstance(resp, int)):
            try:
                resp = int(input("Which one? Enter LNB number: "))
            except ValueError:
                print("Please choose a number")
                continue

            if (resp >= len(defs.lnbs)):
                print("Please choose number from 0 to %u" %(len(defs.lnbs) - 1))
                resp = None
                continue

            lnb = defs.lnbs[resp]
            print("%s %s" %(lnb['vendor'], lnb['model']))
            break
    else:
        lnb = _cfg_custom_lnb(sat)


    if ((lnb['pol'] != "Dual") and (lnb['pol'] != sat['pol'])):
        lnb_pol = "Vertical" if lnb['pol'] == "V" else "Horizontal"
        logging.warning(textwrap.fill(
            "Your LNB has {} polarization and the signal from {} has the "
            "opposite polarization.".format(lnb_pol, sat['name'])))
        input("\nPress Enter to continue...")

    if ((lnb['pol'] == "Dual") and (setup['type'] == defs.sdr_setup_type)):
        print()
        logging.warning(textwrap.fill(
            "Your LNB has dual polarization. Check the voltage of your power "
            "supply in order to discover the polarization on which your LNB "
            "will operate."))
        input("\nPress Enter to continue...")

    if (sat['band'].lower() != lnb['band'].lower()):
        logging.error("The LNB you chose cannot operate " + \
                      "in %s band (band of satellite %s)" %(sat['band'],
                                                            sat['alias']))
        exit(1)

    return lnb


def _cfg_frequencies(sat, setup, lnb):
    """Print summary of frequencies

    Inform the downlink RF frequency, the LNB LO frequency and the L-band
    frequency to be configured in the receiver.

    Args:
        sat   : user's satellite info
        setup : user's setup info
        lnb   : user's LNB info

    """
    util._print_header("Frequencies")
    getcontext().prec = 8

    if (sat['band'].lower() == "ku"):
        if (lnb['universal']):
            assert(isinstance(lnb['lo_freq'], list)), \
                "A Universal LNB must have a list with two LO frequencies"
            assert(len(lnb['lo_freq']) == 2), \
                "A Universal LNB must have two LO frequencies"

            if (sat['dl_freq'] > defs.ku_band_thresh):
                lo_freq = lnb['lo_freq'][1]
            else:
                lo_freq = lnb['lo_freq'][0]
        else:
            lo_freq = lnb['lo_freq']

        if_freq = float(Decimal(sat['dl_freq']) - Decimal(lo_freq))

    elif (sat['band'].lower() == "c"):
        lo_freq = lnb['lo_freq']
        if_freq = float(Decimal(lo_freq) - Decimal(sat['dl_freq']))
    else:
        raise ValueError("Unknown satellite band")

    print("Here are the frequencies of interest:\n")

    print("| Downlink %2s band frequency                     | %8.2f MHz |" %(sat['band'], sat['dl_freq']))
    print("| Your LNB local oscillator (LO) frequency       | %8.2f MHz |" %(lo_freq))
    print("| L-band frequency to configure on your receiver | %7.2f MHz  |" %(if_freq))
    print()

    if (lnb['universal']):
        print("NOTE regarding Universal LNB:\n")
        if (sat['dl_freq'] > defs.ku_band_thresh):
            print(textwrap.fill(("The DL frequency of {} is in Ku high "
                                 "band (> {:.1f} MHz). Hence, you need to use "
                                 "the higher frequency LO ({:.1f} MHz) of your "
                                 "LNB. This requires a 22 kHz tone to be sent "
                                 "to the LNB."
            ).format(sat['alias'], defs.ku_band_thresh, lo_freq)))
            print()
            if (setup['type'] == defs.sdr_setup_type):
                print(textwrap.fill(("With a software-defined setup, you will "
                                     "need to place a 22 kHz tone generator "
                                     "inline between the LNB and the power "
                                     "inserter. Typically the tone generator "
                                     "uses power from the power inserter while "
                                     "delivering the tone directly to the "
                                     "LNB.")))
            else:
                print("The {} {} modem will generate the 22 kHz tone.".format(
                    setup['vendor'], setup['model']))
        else:
            print(textwrap.fill("The DL frequency of {} is in Ku low \
            band (< {:.1f} MHz). Hence, you need to use the lower (default) \
            frequency LO of your LNB.".format(sat['alias'], defs.ku_band_thresh)))

    input("\nPress Enter to continue...")

    return {
        'dl'     : sat['dl_freq'],
        'lo'     : lo_freq,
        'l_band' : if_freq
    }


def _cfg_chan_conf(info, chan_file):
    """Generate the channels.conf file"""

    util._print_header("Channel Configurations for Linux USB Rx")

    print(textwrap.fill("This step will generate the channel configuration "
                        "file that is required when launching the USB "
                        "receiver in Linux.") + "\n")

    if (os.path.isfile(chan_file)):
        print("Found previous %s file:" %(chan_file))

        if (not util._ask_yes_or_no("Remove and regenerate file?")):
            print("Configuration aborted.")
            return
        else:
            os.remove(chan_file)

    with open(chan_file, 'w') as f:
        f.write('[blocksat-ch]\n')
        f.write('\tDELIVERY_SYSTEM = DVBS2\n')
        f.write('\tFREQUENCY = %u\n' %(int(info['sat']['dl_freq']*1000)))
        if (info['sat']['pol'] == 'V'):
            f.write('\tPOLARIZATION = VERTICAL\n')
        else:
            f.write('\tPOLARIZATION = HORIZONTAL\n')
        f.write('\tSYMBOL_RATE = 1000000\n')
        f.write('\tINVERSION = AUTO\n')
        f.write('\tMODULATION = QPSK\n')
        f.write('\tVIDEO_PID = 32+33\n')

    print("File \"%s\" saved." %(chan_file))


def _read_cfg_file(cfg_file):
    """Read configuration file"""

    if (os.path.isfile(cfg_file)):
        with open(cfg_file) as fd:
            info = json.load(fd)
        return info


def _rst_cfg_file(cfg_file):
    """Reset a previous configuration file in case it exists"""
    info = _read_cfg_file(cfg_file)

    if (info is not None):
        print("Found previous configuration:")
        pprint(info, width=40, compact=False)
        if (util._ask_yes_or_no("Reset?")):
            os.remove(cfg_file)
        else:
            print("Configuration aborted.")
            return False
    return True


def read_cfg_file(basename, directory):
    """Read configuration file

    If not available, run configuration helper.

    """
    cfg_file = os.path.join(directory, os.path.basename(basename))
    info = _read_cfg_file(cfg_file)

    while (info is None):
        print("Missing {} configuration file".format(cfg_file))
        if (util._ask_yes_or_no("Run configuration helper now?")):
            configure([])
        else:
            print("Abort")
            return

        info = _read_cfg_file(cfg_file)

    return info


def subparser(subparsers):
    """Argument parser of config command"""
    p = subparsers.add_parser('configure', aliases=['cfg'],
                              description="Configure Blocksat Rx setup",
                              help='Define receiver and Bitcoin FIBRE \
                              configurations',
                              formatter_class=ArgumentDefaultsHelpFormatter)
    p.add_argument('-c', '--chan-conf',
                   default="channels.conf",
                   help='Channel configurations file')
    p.set_defaults(func=configure)
    return p


def configure(args):
    """Configure Blocksat Receiver setup

    """
    cfg_file = os.path.join(args.cfg_dir, os.path.basename(args.cfg_file))
    rst_ok   = _rst_cfg_file(cfg_file)
    if (not rst_ok):
        return

    user_sat   = _cfg_satellite()
    user_setup = _cfg_rx_setup()
    user_lnb   = _cfg_lnb(user_sat, user_setup)
    user_freqs = _cfg_frequencies(user_sat, user_setup, user_lnb)

    user_info = {
        'sat'   : user_sat,
        'setup' : user_setup,
        'lnb'   : user_lnb,
        'freqs' : user_freqs
    }

    logging.debug(pformat(user_info))

    if not os.path.exists(args.cfg_dir):
        os.makedirs(args.cfg_dir)

    with open(cfg_file, 'w') as fd:
        json.dump(user_info, fd)

    util._print_header("JSON configuration file")
    print("Saved configurations on %s" %(cfg_file))

    if (user_setup['type'] == defs.linux_usb_setup_type):
        chan_file = os.path.join(args.cfg_dir, args.chan_conf)
        _cfg_chan_conf(user_info, chan_file)

    util._print_header("Next Steps")

    print(textwrap.fill(
        "Please check setup instructions by running:"))
    print("""
    blocksat-cli instructions
    """)


