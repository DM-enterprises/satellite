"""User setup configuration"""
import os, json, logging
from argparse import ArgumentDefaultsHelpFormatter, Namespace
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

    # Demodulator
    question = "Please, inform your DVB-S2 receiver setup from the list below:"
    setup = util._ask_multiple_choice(
        defs.demods,
        question,
        "Setup",
        lambda x : '{} receiver, using {} demodulator'.format(
            x['type'], (x['vendor'] + " " + x['model']).strip()))

    # Network interface connected to the standalone demodulator
    if (setup['type'] == defs.standalone_setup_type):
        try:
            devices = os.listdir('/sys/class/net/')
        except FileNotFoundError:
            devices = None
            pass

        question = "Which network interface is connected to the {}?".format(
            setup['model'])
        if (devices is not None):
            netdev = util._ask_multiple_choice(devices,
                                               question,
                                               "Interface",
                                               lambda x : '{}'.format(x))
        else:
            netdev = input(question + " ")

        setup['netdev'] = netdev.strip()

    # Antenna
    question = "Please, inform the size of your satellite dish:"
    size = util._ask_multiple_choice(
        defs.antenna_sizes, question, "Size",
        lambda x : '{}'.format(x['label']),
        none_option = True,
        none_str = "Other")

    if (size is None):
        resp = util.input_int("Enter size in cm",
                              "Please enter an integer number in cm")
        size = { 'label' : "custom", 'size' : resp }

    setup['dish_size'] = size

    return setup


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


def _cfg_lnb(sat):
    """Configure LNB - either from preset or from custom specs

    Args:
        sat   : user's satellite info

    """

    util._print_header("LNB")

    question = "Please, inform your LNB model:"
    lnb = util._ask_multiple_choice(
        defs.lnbs, question, "LNB",
        lambda x : "{} {} {}".format(
            x['vendor'], x['model'],
            "(Universal Ku band LNBF)" if x['universal'] else ""),
        none_option = True,
        none_str = "Other")

    if (lnb is None):
        lnb = _cfg_custom_lnb(sat)

    if (sat['band'].lower() != lnb['band'].lower()):
        logging.error("The LNB you chose cannot operate " + \
                      "in %s band (band of satellite %s)" %(sat['band'],
                                                            sat['alias']))
        exit(1)

    return lnb


def _cfg_frequencies(sat, lnb):
    """Print summary of frequencies

    Inform the downlink RF frequency, the LNB LO frequency and the L-band
    frequency to be configured in the receiver.

    Args:
        sat   : user's satellite info
        lnb   : user's LNB info

    """
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
        pprint(info, width=80, compact=False)
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
            configure(Namespace(cfg_dir=directory,
                                cfg_file=basename))
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
    user_lnb   = _cfg_lnb(user_sat)
    user_freqs = _cfg_frequencies(user_sat, user_lnb)

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
        if 'chan_conf' in args:
            chan_file = os.path.join(args.cfg_dir, args.chan_conf)
        else:
            chan_file = os.path.join(args.cfg_dir, "channels.conf")
        _cfg_chan_conf(user_info, chan_file)

    util._print_header("Next Steps")

    print(textwrap.fill(
        "Please check setup instructions by running:"))
    print("""
    blocksat-cli instructions
    """)


