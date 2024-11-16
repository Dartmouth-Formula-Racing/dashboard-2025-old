
var socket = io.connect('http://' + location.hostname + ':' + location.port);

// Interval at which faults element is updated
const FAULT_UPDATE_INTERVAL = 1500; // ms
// List of active faults
var faults = ['Websocket Disconnected'];
var fault_index = 0;


var faults_elm = document.getElementById('faults');
var bot_elm = document.getElementById('bot');
var brb_elm = document.getElementById('brb');
var imd_elm = document.getElementById('imd');
var bms_elm = document.getElementById('bms');
var cvc_elm = document.getElementById('cvc');
var drivestate_elm = document.getElementById('drivestate');

var acctemp_elm = document.getElementById('acctemp');
var leftinvtemp_elm = document.getElementById('leftinvtemp');
var rightinvtemp_elm = document.getElementById('rightinvtemp');

var throttlebar_elm = document.getElementById('throttlebar');
var throttleval_elm = document.getElementById('throttleval');

var rpm_elm = document.getElementById('rpm');
var speed_elm = document.getElementById('speed');
var lap_elm = document.getElementById('lap');
var laptime_elm = document.getElementById('laptime');

var batterybar_elm = document.getElementById('batterybar');
var batteryval_elm = document.getElementById('batteryval');

var hvvoltage_elm = document.getElementById('hvvoltage');
var acccurrent_elm = document.getElementById('acccurrent');
var range_elm = document.getElementById('range');

var tractioncontrol_elm = document.getElementById('tractioncontrol');
var mileage_elm = document.getElementById('mileage');
var vehiclestate_elm = document.getElementById('vehiclestate');


socket.on('connect', function () {
    console.log('Connected to server');
    if (faults.includes('Websocket Disconnected')) {
        faults = faults.filter(fault => fault !== 'Websocket Disconnected');
    }
});

// Log any errors
socket.on('error', function (error) {
    console.log(error);
});

// Log when the server disconnects
socket.on('disconnect', function () {
    console.log('Disconnected from server');
    if (!faults.includes('Websocket Disconnected')) {
        faults.push('Websocket Disconnected');
    }
});

socket.on('data', function (data) {
    if (!data.canconnected) {
        if (!faults.includes('CAN Disconnected')) {
            faults.push('CAN Disconnected');
        }
    } else {
        faults = faults.filter(fault => fault !== 'CAN Disconnected');
    }

    if (data.bot) {
        bot_elm.classList.remove('text-bg-danger');
        bot_elm.classList.add('text-bg-success');
        faults = faults.filter(fault => fault !== 'BOT Pressed');
    } else {
        bot_elm.classList.remove('text-bg-success');
        bot_elm.classList.add('text-bg-danger');
        if (!faults.includes('BOT Pressed')) {
            faults.push('BOT Pressed');
        }
    }

    if (data.brb) {
        brb_elm.classList.remove('text-bg-danger');
        brb_elm.classList.add('text-bg-success');
        faults = faults.filter(fault => fault !== 'BRB Pressed');
    } else {
        brb_elm.classList.remove('text-bg-success');
        brb_elm.classList.add('text-bg-danger');
        if (!faults.includes('BRB Pressed')) {
            faults.push('BRB Pressed');
        }
    }

    if (data.imd) {
        imd_elm.classList.remove('text-bg-danger');
        imd_elm.classList.add('text-bg-success');
        faults = faults.filter(fault => fault !== 'IMD Fault');
    } else {
        imd_elm.classList.remove('text-bg-success');
        imd_elm.classList.add('text-bg-danger');
        if (!faults.includes('IMD Fault')) {
            faults.push('IMD Fault');
        }
    }

    if (data.bms) {
        bms_elm.classList.remove('text-bg-danger');
        bms_elm.classList.add('text-bg-success');
        faults = faults.filter(fault => fault !== 'BMS Fault');
    } else {
        bms_elm.classList.remove('text-bg-success');
        bms_elm.classList.add('text-bg-danger');
        if (!faults.includes('BMS Fault')) {
            faults.push('BMS Fault');
        }
    }

    if (data.cvc_overflow) {
        cvc_elm.classList.remove('text-bg-success');
        cvc_elm.classList.add('text-bg-danger');
    } else {
        cvc_elm.classList.remove('text-bg-danger');
        cvc_elm.classList.add('text-bg-success');
    }
    cvc_elm.innerHTML = data.cvc_time + 'ms';

    // Drive states
    // Drive/Reverse: Green
    // Neutral/Precharging: Yellow
    // Discharged: Red      
    if (data.drive_state.toLowerCase() == 'drive' || data.drive_state.toLowerCase() == 'reverse') {
        drivestate_elm.classList.remove('text-bg-warning');
        drivestate_elm.classList.remove('text-bg-danger');
        drivestate_elm.classList.add('text-bg-success');
    } else if (data.drive_state.toLowerCase() == 'neutral' || data.drive_state.toLowerCase() == 'precharging') {
        drivestate_elm.classList.remove('text-bg-success');
        drivestate_elm.classList.remove('text-bg-danger');
        drivestate_elm.classList.add('text-bg-warning');
    } else {
        drivestate_elm.classList.remove('text-bg-success');
        drivestate_elm.classList.remove('text-bg-warning');
        drivestate_elm.classList.add('text-bg-danger');
    }
    drivestate_elm.innerHTML = data.drive_state;

    acctemp_elm.innerHTML = data.acctemp.toFixed(1) + ' °C';
    leftinvtemp_elm.innerHTML = data.leftinvtemp.toFixed(1) + ' °C';
    rightinvtemp_elm.innerHTML = data.rightinvtemp.toFixed(1) + ' °C';

    throttlebar_elm.style.height = data.throttle_position + '%';
    throttleval_elm.innerHTML = data.throttle_position.toFixed(1) + '%';

    rpm_elm.innerHTML = data.rpm.toFixed(0) + ' RPM';
    speed_elm.innerHTML = data.speed.toFixed(1) + ' MPH';

    lap_elm.innerHTML = 'Lap ' + data.lap;
    laptime_elm.innerHTML = 'Lap time: ' + data.lap_time;

    batterybar_elm.style.height = data.battery_percentage + '%';
    batteryval_elm.innerHTML = data.battery_percentage.toFixed(1) + '%';

    hvvoltage_elm.innerHTML = data.accumulator_voltage.toFixed(1) + ' V';
    acccurrent_elm.innerHTML = data.accumulator_current.toFixed(1) + ' A';
    range_elm.innerHTML = data.estimated_range.toFixed(1) + ' mi';

    if (data.tractioncontrol) {
        tractioncontrol_elm.classList.remove('text-bg-dark');
        tractioncontrol_elm.classList.add('text-bg-success');
        tractioncontrol_elm.innerHTML = 'Traction Control On';
    } else {
        tractioncontrol_elm.classList.remove('text-bg-success');
        tractioncontrol_elm.classList.add('text-bg-dark');
        tractioncontrol_elm.innerHTML = 'Traction Control Off';
    }

    mileage_elm.innerHTML = data.mileage.toFixed(1) + ' Miles';

    vehiclestate_elm.innerHTML = data.vehicle_state;
    // Check if vehicle state contains precharge
    if (data.vehicle_state.toLowerCase().includes('precharge')) {
        // Yellow background
        vehiclestate_elm.classList.remove('text-bg-danger');
        vehiclestate_elm.classList.remove('text-bg-success');
        vehiclestate_elm.classList.remove('text-bg-warning');
        vehiclestate_elm.classList.add('text-bg-warning');
    } else if (data.vehicle_state.toLowerCase() == 'ready to drive' || data.vehicle_state.toLowerCase() == 'buzzer' || data.vehicle_state.toLowerCase() == 'not ready to drive') {
        // Green background
        vehiclestate_elm.classList.remove('text-bg-danger');
        vehiclestate_elm.classList.remove('text-bg-success');
        vehiclestate_elm.classList.remove('text-bg-warning');
        vehiclestate_elm.classList.add('text-bg-success');
    } else if (data.vehicle_state.toLowerCase() == 'charging') {
        // Blue background
        vehiclestate_elm.classList.remove('text-bg-danger');
        vehiclestate_elm.classList.remove('text-bg-success');
        vehiclestate_elm.classList.remove('text-bg-warning');
        vehiclestate_elm.classList.add('text-bg-primary');
    } else {
        // Red background
        vehiclestate_elm.classList.remove('text-bg-primary');
        vehiclestate_elm.classList.remove('text-bg-success');
        vehiclestate_elm.classList.remove('text-bg-warning');
        vehiclestate_elm.classList.add('text-bg-danger');
    }
});


// If no faults, display "No Faults" in green
// Otherwise make background red and cycle through faults
setInterval(function () {
    if (faults.length == 0) {
        faults_elm.innerHTML = 'No Faults';
        faults_elm.classList.remove('text-bg-danger');
        faults_elm.classList.add('text-bg-success');
    } else {
        faults_elm.classList.remove('text-bg-success');
        faults_elm.classList.add('text-bg-danger');
        faults_elm.innerHTML = faults[fault_index];
        fault_index = (fault_index + 1) % faults.length;
    }
}, FAULT_UPDATE_INTERVAL);